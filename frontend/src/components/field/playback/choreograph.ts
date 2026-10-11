/**
 * The choreographer (docs/design/play-playback.md §4): turns one play record into a
 * timeline. A script per play type moves all 22 players so the play ends where the record
 * says: the recorded carrier reaches the recorded spot, where the recorded tacklers meet
 * him. Pure and deterministic: any variation is seeded by the game and the play number.
 *
 * Scripts work in play coordinates: `u` yards downfield from the line of scrimmage (toward
 * the goal the offense attacks; the kicking team's on kicks) and `v` yards from the ball
 * toward the offense's right. `Stage.P` converts them to field coordinates.
 */

import type { GamePlayback, PlaybackPlay, PlaybackPlayer, PlayEvent, TeamSummary } from "@/lib/types";
import { HASH_INSET, LENGTH, WIDTH, fieldX, type Vec3 } from "../layout";
import { defenseSpots, NUMBERS, offenseSpots, spotOnField, TYPICAL, type Package,
         type Spot } from "../players/formations";
import type { Pose } from "../players/poses";
import { blitzers, DEFENSE_PLANS, jobOf, OFFENSE_PLANS, ROUTES, type DefensePlan, type DefenseRole,
         type OffensePlan, type Receiver, type RouteName, type RunScheme } from "./assignments";
import { handsAt, type BallSegment, type Moment, type MomentKind, type PathKey, type PlayTimeline,
         type PoseKey, type TimelinePlayer } from "./timeline";

/** Seconds of pre-snap (players set in their stances) before the snap. */
export const SNAP = 1;
/** Seconds the timeline runs on after the whistle. */
const AFTER = 1.4;
const BALL_REST = 0.12; // ball height lying on the turf
const GOAL_POST_DEPTH = 10; // goal posts stand on the end line

export interface Choreography {
  play: PlaybackPlay;
  timeline: PlayTimeline;
  /** Where the next snap is spotted across the field. */
  nextBallY: number;
}

/** The direction (+1: toward increasing field x) `side` drives in `quarter`: the home team
 * attacks +x in odd quarters, and the teams switch ends every quarter. */
export function driveDirection(quarter: number, side: "home" | "away"): 1 | -1 {
  const home = quarter % 2 === 1 ? 1 : -1;
  return side === "home" ? home : home === 1 ? -1 : 1;
}

/** The ball is spotted where the last play ended, or on the nearer hash if outside them. */
export function hashSpot(y: number): number {
  return Math.min(Math.max(y, HASH_INSET), WIDTH - HASH_INSET);
}

/** Every play of a game, spotting each snap where the previous play ended. */
export function choreographGame(playback: GamePlayback): Choreography[] {
  let ballY = WIDTH / 2;
  return playback.plays.map((play) => {
    const result = choreograph(play, playback, ballY);
    ballY = result.nextBallY;
    return result;
  });
}

// ---------- the stage ----------

type Side = "offense" | "defense";
type Info = Omit<TimelinePlayer, "path" | "poses" | "facing">;
type Point = { x: number; y: number };
type Event<T extends PlayEvent["t"]> = Extract<PlayEvent, { t: T }>;

const clampY = (y: number) => Math.min(Math.max(y, 0.4), WIDTH - 0.4);
const clampX = (x: number) => Math.min(Math.max(x, 0.4), LENGTH - 0.4);
const yardsPerSecond = (speed: number) => 5.6 + speed * 0.042;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

class Actor {
  readonly path: PathKey[];
  readonly poses: PoseKey[] = [];
  readonly speed: number; // yards per second at full speed

  constructor(readonly info: Info, start: Point, readonly facing: number, speed: number) {
    this.path = [{ t: 0, x: clampX(start.x), y: clampY(start.y) }];
    this.speed = yardsPerSecond(speed);
  }

  get end(): PathKey { return this.path[this.path.length - 1]; }

  /** Where he is at `t` (his last key if `t` is past it). */
  at(t: number): Point {
    for (let i = this.path.length - 1; i > 0; i--) {
      const a = this.path[i - 1];
      const b = this.path[i];
      if (t >= a.t) {
        const k = Math.min(1, (t - a.t) / Math.max(1e-6, b.t - a.t));
        return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
      }
    }
    return { x: this.path[0].x, y: this.path[0].y };
  }

  /** Stay put until `t`. */
  hold(t: number): this {
    const e = this.end;
    if (t > e.t + 1e-6) this.path.push({ t, x: e.x, y: e.y });
    return this;
  }

  /** Arrive at `p` at `t` (never earlier than his last key). */
  to(t: number, p: Point): this {
    this.path.push({ t: Math.max(t, this.end.t + 0.02), x: clampX(p.x), y: clampY(p.y) });
    return this;
  }

  /** Run to `p` at `pace` × his top speed, setting off no earlier than `from`. Returns the
   * arrival time. */
  run(from: number, p: Point, pace = 1): number {
    this.hold(from);
    const e = this.end;
    const distance = Math.hypot(clampX(p.x) - e.x, clampY(p.y) - e.y);
    this.to(e.t + distance / (this.speed * pace), p);
    return this.end.t;
  }

  pose(t: number, pose: Pose, options: { span?: number; face?: number } = {}): this {
    this.poses.push({ t, pose, ...options });
    return this;
  }

  toTimeline(duration: number): TimelinePlayer {
    // End every path at the whistle (plus the coda): cut what runs past it, hold what doesn't.
    const end = this.at(duration);
    const path = this.path.filter((k) => k.t < duration - 1e-6);
    path.push({ t: duration, ...end });
    const poses = this.poses.filter((p) => p.t < duration).sort((a, b) => a.t - b.t);
    if (!poses.length || poses[0].t > 0) poses.unshift({ t: 0, pose: "stand" });
    return { ...this.info, facing: this.facing, path, poses };
  }
}

type BallStep =
  | { kind: "held"; from: number; player: Actor }
  | { kind: "flight"; from: number; to: number; start: Actor | Vec3; end: Actor | Vec3; apex: number }
  | { kind: "rest"; from: number; at: Vec3 };

class Stage {
  readonly actors: Actor[] = [];
  readonly ball: BallStep[] = [];
  readonly moments: Moment[] = [];
  /** Players whose part is already scripted, so the generic motions leave them alone. */
  readonly busy = new Set<Actor>();
  flag: { t: number; x: number; y: number } | null = null;
  /** Ids for stand-ins the stage invents (kick units short of players). */
  synthetic = -1000;

  constructor(readonly rng: () => number, readonly d: 1 | -1, readonly los: number,
              readonly ballY: number, readonly roster: Map<number, PlaybackPlayer>) {}

  /** Field coordinates of play coordinates (u downfield, v toward the offense's right). */
  P(u: number, v: number): Point {
    return { x: this.los + this.d * u, y: this.ballY + this.d * v };
  }

  u(p: Point): number { return (p.x - this.los) * this.d; }
  v(p: Point): number { return (p.y - this.ballY) * this.d; }

  /** The facing of a player looking downfield (`toward` +1) or back upfield. */
  face(toward: 1 | -1 = 1): number { return this.d * toward === 1 ? 0 : Math.PI; }

  add(info: Info, at: Point, facing: number, speed: number): Actor {
    const actor = new Actor(info, at, facing, speed);
    this.actors.push(actor);
    return actor;
  }

  byId(id: number | null | undefined): Actor | undefined {
    return id == null ? undefined : this.actors.find((a) => a.info.id === id);
  }

  rest(from: number, at: Vec3) { this.ball.push({ kind: "rest", from, at }); }
  hold(from: number, player: Actor) { this.ball.push({ kind: "held", from, player }); }
  fly(from: number, to: number, start: Actor | Vec3, end: Actor | Vec3, apex: number) {
    this.ball.push({ kind: "flight", from, to, start, end, apex });
  }

  moment(t: number, kind: MomentKind, text: string) { this.moments.push({ t, kind, text }); }

  /** A point `r` yards from `p` toward `q` (away from it for negative `r`). */
  toward(p: Point, q: Point, r: number): Point {
    const dist = Math.hypot(q.x - p.x, q.y - p.y) || 1;
    return { x: p.x + ((q.x - p.x) / dist) * r, y: p.y + ((q.y - p.y) / dist) * r };
  }

  /** The lateral `v` moved inside the numbers enough to stay on the field. */
  inside(v: number, margin = 1.5): number {
    const y = Math.min(Math.max(this.P(0, v).y, margin), WIDTH - margin);
    return this.v({ x: this.los, y });
  }

  range(lo: number, hi: number): number { return lo + (hi - lo) * this.rng(); }
  pick<T>(items: T[]): T { return items[Math.floor(this.rng() * items.length)]; }
}

function find<T extends PlayEvent["t"]>(events: PlayEvent[], t: T): Event<T> | undefined {
  return events.find((e): e is Event<T> => e.t === t);
}

// ---------- players and units ----------

interface Unit {
  actors: Actor[];
  role: Record<string, Actor>;
}

function info(stage: Stage, id: number, side: Side, team: TeamSummary, role: string,
              position: string): Info {
  const player = stage.roster.get(id);
  if (player) {
    return { id, side, teamId: team.id, role, name: player.short_name, number: player.number,
             position: player.position, heightIn: player.height_in, weightLb: player.weight_lb };
  }
  const [height, weight] = TYPICAL[position] ?? TYPICAL.OLB;
  return { id, side, teamId: team.id, role, name: "Stand-in", number: NUMBERS[role] ?? 0,
           position, heightIn: height, weightLb: weight };
}

function addPlayer(stage: Stage, id: number, side: Side, team: TeamSummary, role: string,
                   position: string, at: Point, facing: number): Actor {
  return stage.add(info(stage, id, side, team, role, position), at, facing,
                   stage.roster.get(id)?.speed ?? 60);
}

/** A unit lined up on formation spots, filled by `ids` in order. */
function lineUp(stage: Stage, side: Side, team: TeamSummary, spots: Spot[], ids: number[]): Unit {
  const unit: Unit = { actors: [], role: {} };
  spots.forEach((spot, i) => {
    const place = spotOnField(spot, side, stage.los, stage.ballY, stage.d);
    const actor = addPlayer(stage, ids[i], side, team, spot.role, spot.position, place, place.facing);
    actor.pose(0, spot.stance).hold(SNAP); // set until the snap
    unit.actors.push(actor);
    unit.role[spot.role] = actor;
  });
  return unit;
}

/**
 * Players for a unit the play record doesn't list (kick teams, conversions): the team's
 * players in the game by preferred position, then stand-ins.
 */
class Picker {
  private used = new Set<number>();

  constructor(private stage: Stage, private teamId: number) {}

  take(id: number | null | undefined): number | null {
    if (id == null || this.used.has(id)) return null;
    this.used.add(id);
    return id;
  }

  pick(positions: string[]): number {
    const players = [...this.stage.roster.values()]
      .filter((p) => p.team_id === this.teamId && !this.used.has(p.id))
      .sort((a, b) => a.id - b.id);
    for (const position of positions) {
      const found = players.find((p) => p.position === position);
      if (found) {
        this.used.add(found.id);
        return found.id;
      }
    }
    return this.stage.synthetic--;
  }
}

const COVER = ["OLB", "MLB", "SS", "FS", "CB", "TE", "RB", "WR", "DE"];
const LINE = ["OG", "OT", "C", "TE", "DE", "DT", "OLB"];
const RUSH = ["DE", "DT", "OLB", "MLB"];
const BACKS = ["CB", "FS", "SS", "WR", "RB"];

interface KickSpot { role: string; u: number; v: number; prefs: string[]; id?: number | null; stance?: Pose }

/** A kick unit placed in play coordinates, `toward` the way it faces. */
function kickUnit(stage: Stage, side: Side, team: TeamSummary, spots: KickSpot[],
                  toward: 1 | -1): Unit {
  const picker = new Picker(stage, team.id);
  const unit: Unit = { actors: [], role: {} };
  for (const spot of spots) {
    const id = picker.take(spot.id) ?? picker.pick(spot.prefs);
    const position = stage.roster.get(id)?.position ?? spot.prefs[0];
    const actor = addPlayer(stage, id, side, team, spot.role, position, stage.P(spot.u, spot.v),
                            stage.face(toward));
    actor.pose(0, spot.stance ?? "stand");
    unit.actors.push(actor);
    unit.role[spot.role] = actor;
  }
  return unit;
}

// ---------- shared motions ----------

/** Run toward `target`, stopping `short` yards from it, until `until`. */
function pursue(actor: Actor, from: number, target: Point, until: number, short: number) {
  const start = actor.end.t > from ? actor.end : { ...actor.at(from), t: from };
  const dist = Math.hypot(target.x - start.x, target.y - start.y);
  const travel = Math.min(dist - short, actor.speed * 0.9 * Math.max(0, until - start.t));
  if (travel <= 0.3) return;
  actor.pose(start.t, "run");
  const k = travel / dist;
  const arrive = actor.run(start.t, { x: start.x + (target.x - start.x) * k,
                                      y: start.y + (target.y - start.y) * k }, 0.9);
  actor.pose(arrive, "stand");
}

/** The tacklers converge on the carrier, who goes down where his path ends (at `tEnd`). */
function tackle(stage: Stage, carrier: Actor, tacklers: Actor[], tEnd: number, text?: string) {
  const spot = carrier.end;
  tacklers.forEach((actor, i) => {
    stage.busy.add(actor);
    const from = actor.at(Math.max(SNAP, actor.end.t));
    const angle = Math.atan2(from.y - spot.y, from.x - spot.x) + i * 0.8;
    const at = (r: number) => ({ x: spot.x + Math.cos(angle) * r, y: spot.y + Math.sin(angle) * r });
    const face = angle + Math.PI;
    const start = Math.min(Math.max(actor.end.t, SNAP + 0.3), tEnd - 0.5);
    actor.hold(start).pose(start, "run");
    actor.to(tEnd - 0.3, at(2));
    actor.pose(tEnd - 0.3, "dive", { face }).to(tEnd + 0.1, at(0.7));
    actor.pose(tEnd + 0.35, "down", { face });
  });
  carrier.pose(tEnd, "down");
  if (tacklers.length) {
    stage.moment(tEnd, "tackle", text ?? `Tackled by ${tacklers.map((a) => a.info.name).join(" and ")}`);
  }
}

/** The ball comes loose at `t` and `recoverer` falls on it. */
function fumble(stage: Stage, carrier: Actor, recoverer: Actor, t: number, lost: boolean) {
  const spot = carrier.end;
  const angle = stage.range(0, Math.PI * 2);
  const loose: Vec3 = [clampX(spot.x + Math.cos(angle) * 1.6), clampY(spot.y + Math.sin(angle) * 1.6),
                       BALL_REST];
  stage.fly(t, t + 0.45, carrier, loose, 0.5);
  stage.rest(t + 0.45, loose);
  const reach = Math.max(t + 0.9, recoverer.end.t + 0.3);
  recoverer.pose(Math.max(recoverer.end.t, t + 0.4), "run");
  recoverer.to(reach, stage.toward({ x: loose[0], y: loose[1] }, recoverer.end, 0.4));
  recoverer.pose(reach - 0.15, "down");
  stage.hold(reach, recoverer);
  stage.busy.add(recoverer);
  stage.moment(t, lost ? "turnover" : "contact",
               lost ? `Fumble! Recovered by ${recoverer.info.name}` : "Fumble! The offense recovers");
}

/** The recorded tacklers on the field. */
function tacklersOf(stage: Stage, play: PlaybackPlay, carrier: Actor): Actor[] {
  return (find(play.events, "tackle")?.by ?? []).map((id) => stage.byId(id))
    .filter((a): a is Actor => !!a && a !== carrier);
}

/** After a carry ends at `tEnd`: the touchdown, the tackle, or a stop; then any fumble. */
function finishCarry(stage: Stage, play: PlaybackPlay, carrier: Actor, tEnd: number,
                     scored: boolean, defense: Unit) {
  if (scored) {
    carrier.pose(tEnd, "celebrate");
    stage.moment(tEnd - 0.3, "touchdown", `Touchdown, ${carrier.info.name}!`);
  } else {
    const tacklers = tacklersOf(stage, play, carrier);
    if (tacklers.length) tackle(stage, carrier, tacklers, tEnd);
    else carrier.pose(tEnd, "stand");
  }
  const loose = find(play.events, "fumble");
  if (loose && !scored) {
    const recoverer = loose.lost ? stage.byId(loose.forced_by) ?? defense.actors[0] : carrier;
    fumble(stage, carrier, recoverer, tEnd + 0.05, loose.lost);
  }
}

const LINEMEN = ["LT", "LG", "C", "RG", "RT"];
const FRONT = ["LDE", "LDT", "RDT", "RDE"];
const RECEIVERS: Receiver[] = ["X", "Z", "SLOT", "TE", "RB"];

/** How a line blocks: drive forward (`run`, stepping `lateral` yards toward the play), set
 * and give ground (`pass`), or show pass and then drive (`draw`). */
type BlockMode = "run" | "pass" | "draw";

/** The lines engage at the snap. */
function blockUp(stage: Stage, offense: Unit, defense: Unit, mode: BlockMode, until: number,
                 options: { extra?: Actor[]; lateral?: number } = {}) {
  const blockers = [...LINEMEN.map((r) => offense.role[r]), ...(options.extra ?? [])]
    .filter((a) => a && !stage.busy.has(a));
  const lateral = options.lateral ?? 0;
  const [first, second] = mode === "pass" ? [-1.6, -2.4] : mode === "draw" ? [-1.4, 0.6] : [-0.3, 0.9];
  const ends = new Map<Actor, number>();
  for (const actor of blockers) {
    const v = stage.v(actor.end);
    actor.pose(SNAP, "block", { face: stage.face(1) });
    actor.run(SNAP, stage.P(first, v + lateral * 0.6), mode === "draw" ? 0.35 : 0.6);
    actor.to(until, stage.P(second, v + lateral + stage.range(-0.4, 0.4)));
    actor.pose(until + 0.3, "stand", { face: stage.face(1) });
    ends.set(actor, v + lateral * 0.6);
    stage.busy.add(actor);
  }
  for (const role of FRONT) {
    const actor = defense.role[role];
    if (!actor || stage.busy.has(actor)) continue;
    const v = stage.v(actor.end);
    const opposite = blockers.reduce<Actor | null>((best, b) =>
      !best || Math.abs(ends.get(b)! - v) < Math.abs(ends.get(best)! - v) ? b : best, null);
    const ov = opposite ? ends.get(opposite)! + (v > 0 ? 0.3 : -0.3) : v;
    actor.pose(SNAP, "block", { face: stage.face(-1) });
    actor.run(SNAP, stage.P(first + 0.85, ov), 0.6);
    actor.to(until, stage.P(second + 0.85, ov + stage.range(-0.4, 0.4)));
    actor.pose(until + 0.3, "stand", { face: stage.face(-1) });
    stage.busy.add(actor);
  }
}

/** Everyone still free flows toward the ball, stopping a few yards short. */
function flowTo(stage: Stage, actors: Actor[], from: number, target: Point, until: number) {
  for (const actor of actors) {
    if (actor.end.t > from + 0.05 || actor.poses.some((p) => p.pose === "dive" || p.pose === "down")) continue;
    pursue(actor, from + stage.range(0, 0.3), target, until, stage.range(1.5, 5));
  }
}

// ---------- scrimmage plays ----------

interface Scrimmage {
  stage: Stage;
  play: PlaybackPlay;
  offense: Unit;
  defense: Unit;
  ballOn: number;
  side: 1 | -1; // which way the play goes: toward the offense's right (+1) or left
  plan?: OffensePlan; // the named play's assignments (SIM_VERSION 1.3+)
  defensePlan?: DefensePlan;
  rushers: DefenseRole[]; // who blitzes on this call
}

function scrimmageContext(stage: Stage, play: PlaybackPlay, offense: Unit, defense: Unit,
                          ballOn: number): Scrimmage {
  const plan = OFFENSE_PLANS[String(play.call?.play ?? "")];
  const defensePlan = DEFENSE_PLANS[play.defense?.play ?? ""];
  const onField = new Set(Object.keys(defense.role));
  // Old logs only say whether the defense blitzed: send the middle (or weak) linebacker.
  const legacy = play.defense?.blitz ? (["MIKE", "WILL"] as DefenseRole[]).filter((r) => onField.has(r)).slice(0, 1) : [];
  return {
    stage, play, offense, defense, ballOn, side: stage.rng() < 0.5 ? -1 : 1, plan, defensePlan,
    rushers: defensePlan ? blitzers(defensePlan, onField) : legacy,
  };
}

const DROP: Record<string, number> = { screen: -3.5, short: -5, medium: -7, deep: -8 };
const THROW: Record<string, number> = { screen: 1.2, short: 1.8, medium: 2.4, deep: 2.9 };
const SHOTGUN = new Set(["shotgun", "pistol"]);

/** The snap: handed back under center, or a short flight to a quarterback in the gun.
 * Returns when he has it. */
function snapBall(c: Scrimmage): number {
  const { stage } = c;
  const qb = c.offense.role.QB;
  stage.rest(0, [stage.los, stage.ballY, BALL_REST]);
  stage.moment(SNAP, "snap", "Snap");
  if (!SHOTGUN.has(c.plan?.formation ?? "")) {
    stage.hold(SNAP, qb);
    return SNAP;
  }
  stage.fly(SNAP, SNAP + 0.3, [stage.los, stage.ballY, 0.35], qb, 0.15);
  stage.hold(SNAP + 0.3, qb);
  return SNAP + 0.3;
}

function touchdown(play: PlaybackPlay): boolean {
  return play.result.touchdown === true;
}

/** The carrier's end spot: the recorded gain, or a few yards into the end zone. */
function endU(c: Scrimmage, yards: number, scored: boolean): number {
  return scored ? 100 - c.ballOn + c.stage.range(1.5, 4) : yards;
}

/** A believable finishing lateral: drift from `v`, kept on the field. */
function endV(c: Scrimmage, v: number, yards: number): number {
  return c.stage.inside(v + (c.stage.rng() - 0.5) * Math.min(14, 2 + Math.abs(yards) * 0.5));
}

/** A lineman pulls: back off the line, along behind it, and up through the hole at `holeV`. */
function pull(c: Scrimmage, actor: Actor, holeV: number, until: number) {
  const { stage } = c;
  stage.busy.add(actor);
  const v0 = stage.v(actor.end);
  actor.pose(SNAP, "run");
  actor.to(SNAP + 0.3, stage.P(-1.8, v0));
  actor.to(SNAP + 0.95, stage.P(-1.6, holeV - c.side * 1.2));
  actor.to(SNAP + 1.35, stage.P(0.8, holeV));
  actor.pose(SNAP + 1.35, "block", { face: stage.face(1) });
  actor.to(Math.max(until, SNAP + 1.6), stage.P(2.2, holeV + stage.range(-0.5, 0.5)));
}

function runPlay(c: Scrimmage): number {
  const { stage, play, offense, defense } = c;
  const rush = find(play.events, "rush")!;
  const handoff = find(play.events, "handoff");
  const qb = offense.role.QB;
  const carrier = stage.byId(rush.player) ?? offense.role.RB;
  const scheme: RunScheme = c.plan?.scheme ?? (handoff?.direction === "outside" ? "outside_zone" : "zone");
  const scored = touchdown(play);
  const side = c.side;
  stage.busy.add(qb).add(carrier);
  // Tacklers shed their blocks and pursue rather than block.
  for (const actor of tacklersOf(stage, play, carrier)) stage.busy.add(actor);
  const hasBall = snapBall(c);
  const qbU = stage.u(qb.end);

  // Where the back gets the ball, and the hole he aims for.
  const gapV = side * ({ zone: stage.range(0.9, 3.2), outside_zone: stage.range(6.5, 9),
                         toss: stage.range(7.5, 9.5), power: 3.8, counter: 3.4,
                         draw: stage.range(0, 1.6) } as Record<RunScheme, number>)[scheme];
  let tH = hasBall + 0.3;
  if (carrier !== qb) {
    if (scheme === "toss") {
      // A pitch to the back, already sprinting for the corner.
      const tPitch = hasBall + 0.35;
      tH = tPitch + 0.4;
      qb.pose(SNAP, "run").run(SNAP, stage.P(qbU - 0.8, side * 0.8), 0.4);
      qb.pose(tPitch - 0.15, "throw", { span: 0.3, face: side * stage.d > 0 ? Math.PI / 2 : -Math.PI / 2 });
      qb.pose(tPitch + 0.3, "stand");
      carrier.pose(SNAP, "run").hold(SNAP).to(tH, stage.P(-4.2, side * 4.5));
      stage.fly(tPitch, tH, qb, carrier, 0.6);
      stage.hold(tH, carrier);
      stage.moment(tPitch, "handoff", `Pitch to ${carrier.info.name}`);
    } else {
      // The mesh: under center the QB turns and steps back; in the gun he stays put.
      const draw = scheme === "draw";
      tH = hasBall + (draw ? 1.1 : SHOTGUN.has(c.plan?.formation ?? "") ? 0.45 : 0.75);
      const mesh = qbU > -2.5 ? stage.P(-2, side * 0.7) : stage.P(qbU - (draw ? 1.2 : 0), side * 0.2);
      qb.pose(SNAP, draw ? "stand" : "run", draw ? { face: stage.face(1) } : {});
      qb.run(SNAP, mesh, 0.45);
      qb.hold(tH);
      carrier.pose(SNAP, "run");
      if (scheme === "counter") carrier.to(SNAP + 0.35, { x: carrier.end.x, y: carrier.end.y - stage.d * side * 1 });
      carrier.hold(draw ? tH - 0.5 : SNAP + 0.05)
        .to(tH, { x: mesh.x + stage.d * 0.5, y: mesh.y + stage.d * side * 0.7 });
      stage.hold(tH, carrier);
      stage.moment(tH, "handoff", `Handoff to ${carrier.info.name}`);
      qb.pose(tH + 0.05, "run");
      qb.pose(qb.run(tH + 0.05, stage.P(qbU - 2, -side * 4), 0.6), "stand");
    }
  }
  carrier.pose(tH, "carry");
  const u = endU(c, rush.yards, scored);
  if (u >= 1) {
    if (scheme === "outside_zone" || scheme === "toss") carrier.run(tH, stage.P(-1.2, gapV * 0.85), 0.85);
    // Power and counter wait a beat for the pulling guard to lead through the hole.
    carrier.run(scheme === "power" || scheme === "counter" ? Math.max(tH, SNAP + 0.9) : tH,
                stage.P(0.5, gapV), 0.85);
    carrier.run(tH, stage.P(u, endV(c, gapV, u)), 0.95);
  } else {
    carrier.run(tH, stage.P(u, gapV * 0.7), 0.7);
  }
  const tEnd = carrier.end.t;

  // The line: pullers lead, everyone else blocks the scheme.
  const backside = (role: string) => offense.role[role] && stage.v(offense.role[role].path[0]) * side < 0;
  const guard = ["LG", "RG"].find(backside);
  const tackle = ["LT", "RT"].find(backside);
  if (scheme === "power" && guard) pull(c, offense.role[guard], gapV, tEnd);
  if (scheme === "counter") {
    if (guard) pull(c, offense.role[guard], gapV, tEnd);
    if (tackle) pull(c, offense.role[tackle], gapV + side * 1.2, tEnd);
  }
  const lateral = side * ({ zone: 1.2, outside_zone: 2.5, toss: 2.5, power: -0.8, counter: -0.8,
                            draw: 0 } as Record<RunScheme, number>)[scheme];
  blockUp(stage, offense, defense, scheme === "draw" ? "draw" : "run", tEnd,
          { extra: offense.role.TE ? [offense.role.TE] : [], lateral });
  finishCarry(stage, play, carrier, tEnd, scored, defense);
  // Receivers block downfield; the defense flows to the ball.
  for (const role of ["X", "Z", "SLOT"]) {
    const actor = offense.role[role];
    if (!actor || stage.busy.has(actor)) continue;
    const v = stage.v(actor.end);
    actor.pose(SNAP, "run");
    actor.pose(actor.run(SNAP + 0.1, stage.P(stage.range(4, 8), v * 0.85), 0.8), "block",
               { face: stage.face(1) });
  }
  flowTo(stage, defense.actors.filter((a) => !stage.busy.has(a)), SNAP + 0.3, carrier.end, tEnd + 0.4);
  return tEnd;
}

/** The route a receiver runs on this play, or null if he blocks. */
function routeOf(c: Scrimmage, actor: Actor): RouteName | null {
  const name = c.plan?.routes?.[actor.info.role as Receiver];
  return name && name !== "block" ? name : null;
}

/**
 * Waypoints of a named route from the receiver's alignment. For the target, `catchU` (the
 * recorded air yards) stretches the route so the last point is where the ball arrives.
 */
function drawRoute(c: Scrimmage, actor: Actor, name: RouteName, catchU?: number): Point[] {
  const { stage } = c;
  const u0 = stage.u(actor.end);
  const v0 = stage.v(actor.end);
  // Toward the middle; the back's "inside" is away from the side the play goes.
  const inward = actor.info.role === "RB" ? -c.side : v0 > 0 ? -1 : 1;
  const points = ROUTES[name];
  const last = points[points.length - 1][0];
  const stretch = catchU !== undefined && last > 0.5 && catchU > u0 + 0.5 ? (catchU - u0) / last : 1;
  return points.map(([du, din], i) => {
    const deep = i === points.length - 1 && catchU !== undefined && stretch === 1 ? catchU : u0 + du * stretch;
    return stage.P(deep, stage.inside(v0 + inward * din));
  });
}

/** The old improvised route (play logs without a named play): something fitting the depth. */
function improvisedRoute(c: Scrimmage, actor: Actor, depth: number): Point[] {
  const { stage } = c;
  const u0 = stage.u(actor.end);
  const v0 = stage.v(actor.end);
  const inward = v0 > 0 ? -1 : 1;
  if (actor.info.role === "RB") return [stage.P(Math.max(-2, depth), stage.inside(c.side * stage.range(5, 9)))];
  if (depth < 1) return [stage.P(depth, stage.inside(v0 - inward * 2))]; // a screen: step out wide
  const kind = depth >= 18 ? "go" : stage.pick(["out", "in", "curl", "slant"]);
  const v = stage.inside(kind === "go" ? v0 + stage.range(-2, 2)
    : kind === "out" ? v0 - inward * stage.range(3, 6)
      : kind === "in" ? v0 + inward * stage.range(5, 9)
        : kind === "slant" ? v0 + inward * stage.range(4, 7) : v0);
  if (kind === "go" || kind === "slant") return [stage.P(Math.min(depth, u0 + 2), v0), stage.P(depth, v)];
  if (kind === "curl") return [stage.P(depth + 2, v0), stage.P(depth, v)];
  return [stage.P(depth - 0.5, v0), stage.P(depth, v)];
}

/** The target's route to the catch point `catchU` yards downfield. */
function targetRoute(c: Scrimmage, actor: Actor, catchU: number): Point[] {
  const name = routeOf(c, actor);
  if (name) return drawRoute(c, actor, name, catchU);
  // Thrown to a man the play had blocking: he leaks out late into the flat.
  if (c.plan) return drawRoute(c, actor, catchU >= 4 ? "sit" : "flat", catchU);
  return improvisedRoute(c, actor, catchU);
}

function pathLength(from: Point, points: Point[]): number {
  let total = 0;
  let at = from;
  for (const p of points) {
    total += Math.hypot(p.x - at.x, p.y - at.y);
    at = p;
  }
  return total;
}

// Coverage for play logs without a named defensive call.
const LEGACY_MAN: Record<string, Receiver[]> = {
  CB1: ["X"], CB2: ["Z"], NB: ["SLOT"], DB: ["TE"], SAM: ["TE"], WILL: ["RB"], MIKE: ["RB", "TE"],
};
const LEGACY_ZONE: Record<string, [number, number]> = {
  CB1: [13, -15], CB2: [13, 15], NB: [5, -11], DB: [5, 11], SAM: [7, 6], WILL: [7, -6],
  MIKE: [8, 0], FS: [18, -7], SS: [16, 7],
};

/** Trail `mark` a step behind, shading inside and deep, until `until`. */
function trail(c: Scrimmage, actor: Actor, mark: Actor, until: number) {
  const { stage } = c;
  const v = stage.v(mark.path[0]) > 0 ? -0.7 : 0.7;
  for (let t = SNAP + 0.4; t < until; t += 0.35) {
    const p = mark.at(t - 0.25);
    actor.to(t, { x: p.x + stage.d * 0.9, y: p.y + stage.d * v });
  }
}

/**
 * Everyone not yet scripted on a pass play: receivers run the play's routes (or block),
 * blitzers rush, and the coverage plays the call until `until`. The rest of the defensive
 * front is left to `blockUp`.
 */
function passFlow(c: Scrimmage, until: number, qbAt: Point) {
  const { stage, play, offense, defense } = c;
  const running = new Set<Actor>();
  for (const role of RECEIVERS) {
    const actor = offense.role[role];
    if (!actor || stage.busy.has(actor)) continue;
    stage.busy.add(actor);
    const name = routeOf(c, actor);
    const blocks = c.plan ? !name : (role === "RB" || role === "TE") && stage.rng() < 0.5;
    if (blocks) {
      if (c.plan?.screen || c.plan?.routes?.SLOT === "bubble") { // stalk the nearest defender
        actor.pose(SNAP, "run").pose(actor.run(SNAP, stage.P(stage.range(2, 4), stage.v(actor.end) * 0.9), 0.7),
                                     "block", { face: stage.face(1) });
        continue;
      }
      const at = role === "RB" ? stage.P(Math.min(stage.u(qbAt) + 2, -3), c.side * 1.6)
        : stage.P(-1.5, stage.v(actor.end));
      actor.pose(SNAP, "run").pose(actor.run(SNAP, at, 0.6), "block", { face: stage.face(1) });
      continue;
    }
    actor.pose(SNAP, "run");
    let t = SNAP + 0.1;
    const points = name ? drawRoute(c, actor, name)
      : improvisedRoute(c, actor, role === "RB" ? stage.range(1, 4) : stage.range(5, 22));
    for (const p of points) t = actor.run(t, p);
    actor.pose(t, "stand");
    running.add(actor);
  }
  for (const actor of defense.actors) {
    const role = actor.info.role;
    if (stage.busy.has(actor)) continue;
    const job = c.defensePlan ? jobOf(c.defensePlan, role, c.rushers) : null;
    if (c.rushers.includes(role as DefenseRole)) {
      rush(c, actor, qbAt, Math.min(until, SNAP + 2.6), 2.2);
      continue;
    }
    if (FRONT.includes(role) && !(job && "zone" in job)) continue; // rushes: blockUp
    stage.busy.add(actor);
    actor.pose(SNAP, "run");
    const legacyMark = !c.defensePlan && play.defense?.coverage === "man"
      ? (LEGACY_MAN[role] ?? []).map((r) => offense.role[r]).find((r) => r && running.has(r)) : undefined;
    const mark = job && "man" in job ? offense.role[job.man] : legacyMark;
    if (mark && running.has(mark)) {
      if (!c.defensePlan) running.delete(mark);
      trail(c, actor, mark, until);
      continue;
    }
    // A zone, or a man defender whose man stayed in to block: sit underneath him.
    const spot: [number, number] = job && "zone" in job ? job.zone
      : mark ? [5, stage.v(mark.path[0])] : LEGACY_ZONE[role] ?? [6, stage.v(actor.end)];
    actor.pose(actor.run(SNAP + 0.1, stage.P(spot[0], stage.inside(spot[1])), 0.7), "stand",
               { face: stage.face(-1) });
  }
}

/** The quarterback's drop, with any play-action fake first. Returns when he's set, and
 * where. */
function dropBack(c: Scrimmage, depth: string, hasBall: number): { set: number; at: Point } {
  const { stage, offense } = c;
  const qb = offense.role.QB;
  const rb = offense.role.RB;
  stage.busy.add(qb);
  const u0 = stage.u(qb.end);
  const deep = Math.min(DROP[depth] ?? DROP.short, u0 - 1);
  const action = c.plan?.playAction;
  if (action && rb && !stage.busy.has(rb)) {
    // The fake: meet the back as if handing off, then turn and set up (or roll out).
    const tFake = hasBall + 0.7;
    const mesh = stage.P(Math.min(u0, -2.2), c.side * 0.7);
    qb.pose(SNAP, "run").run(SNAP, mesh, 0.45);
    qb.hold(tFake);
    rb.pose(SNAP, "run").to(tFake, { x: mesh.x + stage.d * 0.5, y: mesh.y + stage.d * c.side * 0.7 });
    rb.run(tFake, stage.P(0.5, c.side * 2.5), 0.8);
    rb.pose(rb.end.t, "block", { face: stage.face(1) });
    stage.busy.add(rb);
    stage.moment(tFake, "handoff", "Play-action fake");
    const at = action === "boot" ? stage.P(DROP.short - 1, stage.inside(-c.side * 7, 4)) : stage.P(deep, 0);
    qb.pose(tFake + 0.05, "run", action === "boot" ? {} : { face: stage.face(1) });
    const set = qb.run(tFake + 0.05, at, action === "boot" ? 0.8 : 0.6);
    qb.pose(set, "stand", { face: stage.face(1) });
    return { set, at: qb.end };
  }
  qb.pose(SNAP, "run", { face: stage.face(1) });
  const set = qb.run(hasBall, stage.P(c.plan?.screen ? Math.min(deep, -7) : deep, 0), 0.62);
  qb.pose(set, "stand", { face: stage.face(1) });
  return { set, at: qb.end };
}

/** A defender who comes free, around the edge or up the middle, closing on the QB by `t`. */
function rush(c: Scrimmage, actor: Actor, qbAt: Point, t: number, short: number) {
  const { stage } = c;
  stage.busy.add(actor);
  const v = stage.v(actor.end);
  actor.pose(SNAP, "run");
  if (Math.abs(v) > 2) actor.run(SNAP, stage.P(-1.5, v * 1.2), 0.9);
  actor.to(t, stage.toward(qbAt, actor.end, short));
}

/** On a screen the line sets, lets the rush through, then releases downfield to lead the
 * catch; the rushers chase the quarterback. */
function screenBlocks(c: Scrimmage, qbAt: Point, tThrow: number) {
  const { stage, offense, defense } = c;
  for (const role of FRONT) {
    const actor = defense.role[role];
    if (actor && !stage.busy.has(actor)) rush(c, actor, qbAt, tThrow + 0.1, stage.range(1.5, 3));
  }
  LINEMEN.forEach((role, i) => {
    const actor = offense.role[role];
    if (!actor || stage.busy.has(actor)) return;
    stage.busy.add(actor);
    const v = stage.v(actor.end);
    actor.pose(SNAP, "block", { face: stage.face(1) });
    actor.run(SNAP, stage.P(-1.2, v), 0.5);
    actor.hold(tThrow - 0.6).pose(tThrow - 0.6, "run");
    actor.to(tThrow + 0.6, stage.P(stage.range(1, 3), stage.inside(c.side * (5 + i * 1.5))));
    actor.pose(tThrow + 0.6, "block", { face: stage.face(1) });
  });
}

function passPlay(c: Scrimmage): number {
  const { stage, play, offense, defense } = c;
  const pass = find(play.events, "pass")!;
  const depth = find(play.events, "dropback")?.depth ?? "short";
  const qb = offense.role.QB;
  const target = stage.byId(pass.target);
  const picked = pass.result === "interception" ? find(play.events, "interception") : undefined;
  const defended = find(play.events, "pass_defended");
  const scored = touchdown(play);
  const hasBall = snapBall(c);
  const { set, at: qbAt } = dropBack(c, depth, hasBall);

  // Where the ball goes, and when.
  const air = Math.min(pass.air, 100 - c.ballOn + 8);
  let catchAt: Point;
  let routeTime = 0;
  if (target) {
    stage.busy.add(target);
    const points = targetRoute(c, target, pass.result === "complete" ? Math.min(air, pass.yards) : air);
    catchAt = points[points.length - 1];
    routeTime = pathLength(target.end, points) / target.speed + 0.15;
    target.pose(SNAP, "run");
    for (const p of points.slice(0, -1)) target.run(SNAP + 0.1, p);
  } else { // thrown away, out of bounds on the near side
    catchAt = { x: stage.P(stage.range(6, 14), 0).x, y: stage.ballY < WIDTH / 2 ? -2 : WIDTH + 2 };
  }
  const throwDist = Math.hypot(catchAt.x - qbAt.x, catchAt.y - qbAt.y);
  const flight = 0.3 + throwDist / 22;
  const pressure = !!find(play.events, "pressure");
  const planned = SNAP + THROW[depth] + stage.range(0, 0.35) - (pressure ? 0.3 : 0);
  const tCatch = Math.max(planned + flight, SNAP + routeTime, set + 0.3 + flight);
  const tThrow = tCatch - flight;
  const apex = 0.4 + throwDist * 0.09;
  const face = Math.atan2(catchAt.y - qbAt.y, catchAt.x - qbAt.x);
  const receiveFace = face + Math.PI;
  qb.pose(tThrow - 0.3, "throw", { span: 0.45, face }).pose(tThrow + 0.35, "stand", { face });
  stage.moment(tThrow, "throw", target ? `${qb.info.name} throws for ${target.info.name}`
    : `${qb.info.name} throws it away`);

  if (pressure) {
    const rusher = stage.pick([defense.role.LDE, defense.role.RDE].filter((a) => a && !stage.busy.has(a)));
    if (rusher) rush(c, rusher, qbAt, tThrow + 0.05, 1.2);
  }
  for (const role of c.rushers) {
    const blitzer = defense.role[role];
    if (blitzer && !stage.busy.has(blitzer)) rush(c, blitzer, qbAt, tThrow, 2.2);
  }
  const thief = picked ? stage.byId(picked.by) ?? defense.role.FS : undefined;
  const breakup = defended && !thief ? stage.byId(defended.by) : undefined;
  for (const defender of [thief, breakup]) {
    if (!defender) continue;
    stage.busy.add(defender);
    defender.pose(SNAP, "run").to(tCatch - 0.3, stage.toward(catchAt, defender.end, defender === thief ? 0.9 : 1.8));
  }
  if (target) target.to(tCatch, thief ? stage.toward(catchAt, thief.end, -1.2) : catchAt);
  // Front-seven tacklers on a short pass shed their blocks; the rest cover until the catch.
  const tacklers = target ? tacklersOf(stage, play, target) : [];
  for (const actor of tacklers) if (FRONT.includes(actor.info.role)) stage.busy.add(actor);
  if (c.plan?.screen) screenBlocks(c, qbAt, tThrow);
  passFlow(c, tCatch, qbAt);
  blockUp(stage, offense, defense, "pass", Math.max(tThrow, set));

  let tEnd = tCatch + 0.4;
  let ballEnd: Point = catchAt;
  if (thief && picked) {
    thief.to(tCatch, stage.toward(catchAt, qbAt, 0.4)).pose(tCatch - 0.35, "catch", { face: receiveFace });
    stage.fly(tThrow, tCatch, qb, thief, apex);
    stage.hold(tCatch, thief);
    stage.moment(tCatch, "turnover", `Intercepted by ${thief.info.name}!`);
    const back = scored ? -c.ballOn - stage.range(1.5, 4) : stage.u(catchAt) - picked.return;
    thief.pose(tCatch + 0.15, "carry");
    tEnd = thief.run(tCatch + 0.15, stage.P(back, endV(c, stage.v(catchAt), picked.return)), 0.95);
    if (scored) {
      thief.pose(tEnd, "celebrate");
      stage.moment(tEnd - 0.3, "touchdown", `Pick six, ${thief.info.name}!`);
    } else {
      tackle(stage, thief, tacklers.length ? tacklers : [target ?? qb], tEnd);
    }
    ballEnd = thief.end;
  } else if (target && pass.result === "complete") {
    target.pose(tCatch - 0.35, "catch", { face: receiveFace });
    stage.fly(tThrow, tCatch, qb, target, apex);
    stage.hold(tCatch, target);
    stage.moment(tCatch, "catch", `Caught by ${target.info.name}`);
    target.pose(tCatch + 0.12, "carry");
    const u = endU(c, pass.yards, scored);
    tEnd = u > stage.u(catchAt) + 0.3
      ? target.run(tCatch + 0.12, stage.P(u, endV(c, stage.v(catchAt), u - air)), 0.95)
      : target.hold(tCatch + 0.3).end.t;
    finishCarry(stage, play, target, tEnd, scored, defense);
    ballEnd = target.end;
  } else if (target) {
    target.pose(tCatch - 0.35, "catch", { face: receiveFace }).pose(tCatch + 0.4, "stand");
    const past = stage.toward(catchAt, qbAt, -stage.range(1, 3));
    const drop: Vec3 = [clampX(past.x), clampY(past.y), BALL_REST];
    stage.fly(tThrow, tCatch, qb, [catchAt.x, catchAt.y, 1.5], apex);
    stage.fly(tCatch, tCatch + 0.45, [catchAt.x, catchAt.y, 1.5], drop, 0.4);
    stage.rest(tCatch + 0.45, drop);
    if (breakup) {
      breakup.pose(tCatch - 0.3, "dive", { face: receiveFace + Math.PI })
        .to(tCatch + 0.1, stage.toward(catchAt, breakup.end, 0.7))
        .pose(tCatch + 0.4, "down", { face: receiveFace + Math.PI });
      stage.moment(tCatch, "contact", `Broken up by ${breakup.info.name}`);
    } else {
      stage.moment(tCatch, "contact", "Incomplete");
    }
  } else {
    const landing: Vec3 = [catchAt.x, catchAt.y, BALL_REST];
    stage.fly(tThrow, tCatch, qb, landing, apex);
    stage.rest(tCatch, landing);
  }
  flowTo(stage, defense.actors, tCatch, ballEnd, tEnd + 0.4);
  return tEnd;
}

function sackPlay(c: Scrimmage): number {
  const { stage, play, offense, defense } = c;
  const sack = find(play.events, "sack")!;
  const qb = offense.role.QB;
  const hasBall = snapBall(c);
  const { set } = dropBack(c, find(play.events, "dropback")?.depth ?? "medium", hasBall);
  const tSack = Math.max(set + 0.4, SNAP + stage.range(2.2, 3));
  qb.to(tSack - 0.05, stage.P(sack.yards, stage.range(-1.2, 1.2)));
  const sacker = stage.byId(sack.by) ?? defense.role.RDE;
  rush(c, sacker, qb.end, tSack - 0.5, 2.2);
  passFlow(c, tSack, qb.end);
  blockUp(stage, offense, defense, "pass", tSack);
  tackle(stage, qb, [sacker], tSack, `Sacked by ${sacker.info.name}`);
  const loose = find(play.events, "fumble");
  if (loose) fumble(stage, qb, loose.lost ? sacker : offense.role.C, tSack + 0.05, loose.lost);
  flowTo(stage, defense.actors, tSack, qb.end, tSack + 0.6);
  return tSack;
}

function scramblePlay(c: Scrimmage): number {
  const { stage, play, offense, defense } = c;
  const scramble = find(play.events, "scramble")!;
  const qb = offense.role.QB;
  const scored = touchdown(play);
  const hasBall = snapBall(c);
  const { set, at } = dropBack(c, find(play.events, "dropback")?.depth ?? "medium", hasBall);
  const tRun = Math.max(set + 0.5, SNAP + stage.range(2, 2.6));
  qb.hold(tRun).pose(tRun, "carry");
  qb.run(tRun, stage.P(stage.u(at) + 1, stage.inside(stage.v(at) + c.side * 4)), 0.8);
  const u = endU(c, scramble.yards, scored);
  const tEnd = qb.run(tRun, stage.P(u, endV(c, c.side * stage.range(5, 10), u)), 0.95);
  stage.moment(tRun, "contact", `${qb.info.name} scrambles`);
  passFlow(c, tRun + 0.4, at);
  blockUp(stage, offense, defense, "pass", tRun + 0.4);
  finishCarry(stage, play, qb, tEnd, scored, defense);
  flowTo(stage, defense.actors, tRun + 0.4, qb.end, tEnd + 0.4);
  return tEnd;
}

function kneelPlay(c: Scrimmage): number {
  const { stage, play, offense } = c;
  const kneel = find(play.events, "kneel")!;
  const qb = offense.role.QB;
  snapBall(c);
  qb.to(SNAP + 0.5, stage.P(Math.min(kneel.yards, -0.5), 0)).pose(SNAP + 0.45, "kneel", { face: stage.face(1) });
  for (const actor of stage.actors) if (actor !== qb) actor.pose(SNAP + 0.3, "stand");
  stage.moment(SNAP + 0.6, "tackle", `${qb.info.name} takes a knee`);
  return SNAP + 1;
}

/** A pre-snap foul: the offender moves early, the flag flies, and everyone stands up. */
function preSnapFoul(c: Scrimmage, penalty: Event<"penalty">): number {
  const { stage } = c;
  stage.rest(0, [stage.los, stage.ballY, BALL_REST]);
  const offender = stage.byId(penalty.player);
  const t = SNAP - 0.15;
  if (offender) {
    const toward = offender.info.side === "offense" ? 1 : -1;
    const p = offender.end;
    offender.hold(t).to(t + 0.35, { x: p.x + stage.d * toward * 0.7, y: p.y }).pose(t + 0.1, "stand");
  }
  for (const actor of stage.actors) if (actor !== offender) actor.pose(SNAP + 0.3, "stand");
  return SNAP + 0.6;
}

function scrimmage(play: PlaybackPlay, stage: Stage, offenseTeam: TeamSummary,
                   defenseTeam: TeamSummary): number {
  const personnel = play.personnel;
  const pkg = (personnel?.package ?? play.defense?.package ?? "base") as Package;
  const ours = new Picker(stage, offenseTeam.id);
  const theirs = new Picker(stage, defenseTeam.id);
  const formation = OFFENSE_PLANS[String(play.call?.play ?? "")]?.formation;
  const spots = offenseSpots(formation);
  const offense = lineUp(stage, "offense", offenseTeam, spots,
                         personnel?.offense ?? spots.map((s) => ours.pick([s.position])));
  const defense = lineUp(stage, "defense", defenseTeam, defenseSpots(pkg),
                         personnel?.defense ?? defenseSpots(pkg).map((s) => theirs.pick([s.position])));
  const c = scrimmageContext(stage, play, offense, defense, play.ball_on ?? 25);
  const events = play.events;
  const penalty = find(events, "penalty");
  if (find(events, "kneel")) return kneelPlay(c);
  if (find(events, "sack")) return sackPlay(c);
  if (find(events, "scramble")) return scramblePlay(c);
  if (find(events, "pass")) return passPlay(c);
  if (find(events, "rush")) return runPlay(c);
  if (penalty) return preSnapFoul(c, penalty);
  stage.rest(0, [stage.los, stage.ballY, BALL_REST]);
  return SNAP + 0.5;
}

// ---------- kicks ----------

function kickoff(play: PlaybackPlay, stage: Stage, kicking: TeamSummary, receiving: TeamSummary): number {
  const kick = find(play.events, "kickoff")!;
  const cover = kickUnit(stage, "offense", kicking, [
    { role: "K", u: -7, v: 0, prefs: ["K"], id: kick.kicker },
    ...[-22, -17, -12, -7, -3, 3, 7, 12, 17, 22].map((v, i) => ({ role: `L${i + 1}`, u: -5, v, prefs: COVER })),
  ], 1);
  const ret = kickUnit(stage, "defense", receiving, [
    { role: "KR", u: 62, v: 0, prefs: ["RB", "WR", "CB"], id: kick.returner },
    { role: "KR2", u: 57, v: 6, prefs: BACKS },
    ...[-15, -8, 0, 8, 15].map((v, i) => ({ role: `F${i + 1}`, u: 20, v, prefs: COVER })),
    ...[-10, -3, 3, 10].map((v, i) => ({ role: `M${i + 1}`, u: 38, v, prefs: LINE })),
  ], -1);
  const kicker = cover.role.K;
  const returner = ret.role.KR;
  const tKick = 1.6;
  const tLand = tKick + stage.range(3.8, 4.3);
  const tee: Vec3 = [stage.los, stage.ballY, 0.2];
  stage.rest(0, tee);
  kicker.pose(0.4, "run").hold(0.4).to(tKick, stage.P(-0.3, 0));
  kicker.pose(tKick - 0.2, "kick", { span: 0.4, face: stage.face(1) });
  stage.moment(tKick, "kick", `${kicker.info.name} kicks off`);
  for (const actor of cover.actors.slice(1)) {
    actor.pose(0.6, "run").hold(0.6).to(tKick, stage.P(0, stage.v(actor.end)));
  }

  const landU = kick.touchback ? stage.range(66, 71) : stage.range(58, 63);
  const landV = stage.range(-6, 6);
  returner.pose(0.8, "run").hold(0.8).to(tLand, stage.P(landU, landV));
  returner.pose(tLand - 0.35, "catch", { face: stage.face(-1) });
  stage.fly(tKick, tLand, tee, returner, 22);
  stage.hold(tLand, returner);
  stage.moment(tLand, "catch", `${returner.info.name} fields it`);
  let tEnd = tLand + 0.6;
  if (kick.touchback) {
    returner.pose(tLand + 0.3, "kneel", { face: stage.face(-1) });
    stage.moment(tLand + 0.4, "whistle", "Touchback");
  } else {
    // The return, up the field to the recorded spot (yards from the receiving goal line).
    returner.pose(tLand + 0.2, "carry");
    tEnd = returner.run(tLand + 0.2, stage.P(65 - kick.return, stage.inside(landV + stage.range(-8, 8))), 0.95);
    const end = returner.end;
    const tackler = cover.actors.slice(1).reduce((best, a) =>
      Math.abs(a.end.y - end.y) < Math.abs(best.end.y - end.y) ? a : best);
    tackler.pose(tKick, "run").to(tEnd - 0.6, stage.toward(end, tackler.end, 3));
    tackle(stage, returner, [tackler], tEnd);
  }
  const end = returner.end;
  flowTo(stage, cover.actors.slice(1), tKick, end, tEnd + 0.3);
  pursue(kicker, tKick + 0.4, end, tEnd, 12);
  for (const actor of ret.actors.slice(1)) {
    const spot = stage.P(Math.max(stage.u(end) + stage.range(4, 12), stage.u(actor.end) - 25),
                         stage.v(actor.end) * 0.7);
    actor.pose(tKick, "run").pose(actor.run(tKick + 0.2, spot, 0.8), "block", { face: stage.face(1) });
  }
  return tEnd;
}

function punt(play: PlaybackPlay, stage: Stage, kicking: TeamSummary, receiving: TeamSummary): number {
  const kick = find(play.events, "punt")!;
  const ballOn = play.ball_on ?? 30;
  const landU = Math.min(kick.yards, 100 - ballOn);
  const landV = stage.range(-5, 5);
  const line = [-5.4, -3.6, -1.8, 1.8, 3.6, 5.4];
  const cover = kickUnit(stage, "offense", kicking, [
    { role: "P", u: -14, v: 0, prefs: ["P"], id: kick.punter },
    { role: "LS", u: -0.7, v: 0, prefs: ["C", "OG"], stance: "stance3" },
    ...line.map((v, i) => ({ role: `L${i + 1}`, u: -0.9, v, prefs: LINE, stance: "stance3" as const })),
    { role: "PP", u: -5.5, v: 1, prefs: ["SS", "FS", "MLB", "RB"] },
    { role: "G1", u: -1, v: stage.inside(-20, 2), prefs: BACKS, stance: "stance2" },
    { role: "G2", u: -1, v: stage.inside(20, 2), prefs: BACKS, stance: "stance2" },
  ], 1);
  const ret = kickUnit(stage, "defense", receiving, [
    { role: "PR", u: landU + stage.range(-1, 1), v: landV, prefs: ["WR", "CB", "RB"], id: kick.returner },
    ...[-4.5, -2.5, -0.8, 0.8, 2.5, 4.5].map((v, i) => ({ role: `R${i + 1}`, u: 1, v, prefs: RUSH,
                                                         stance: "stance3" as const })),
    { role: "J1", u: 1, v: stage.inside(-19, 2), prefs: BACKS, stance: "stance2" },
    { role: "J2", u: 1, v: stage.inside(19, 2), prefs: BACKS, stance: "stance2" },
    { role: "H1", u: 10, v: -6, prefs: COVER },
    { role: "H2", u: 10, v: 6, prefs: COVER },
  ], -1);
  const punter = cover.role.P;
  const returner = ret.role.PR;
  const tReceive = SNAP + 0.75;
  const tKick = tReceive + 1.2;
  const tLand = tKick + stage.range(4, 4.6);
  stage.rest(0, [stage.los, stage.ballY, BALL_REST]);
  stage.fly(SNAP, tReceive, [stage.los, stage.ballY, 0.4], punter, 0.2);
  stage.hold(tReceive, punter);
  stage.moment(SNAP, "snap", "Snap to the punter");
  punter.hold(tReceive).to(tKick, stage.P(-12, 0));
  punter.pose(tKick - 0.2, "kick", { span: 0.4, face: stage.face(1) }).pose(tKick + 0.3, "stand");
  stage.moment(tKick, "kick", `${punter.info.name} punts`);

  const landing = stage.P(landU, landV);
  let tEnd: number;
  if (kick.touchback) {
    const bounce: Vec3 = [stage.P(100 - ballOn + 6, 0).x, landing.y, BALL_REST];
    stage.fly(tKick, tLand, punter, [landing.x, landing.y, BALL_REST], 18);
    stage.fly(tLand, tLand + 0.8, [landing.x, landing.y, BALL_REST], bounce, 1.2);
    stage.rest(tLand + 0.8, bounce);
    stage.moment(tLand + 0.8, "whistle", "Touchback");
    returner.pose(SNAP, "run").run(SNAP + 1, stage.P(landU - 8, landV), 0.5);
    returner.pose(returner.end.t, "stand");
    tEnd = tLand + 0.8;
  } else {
    returner.to(tLand, landing).pose(tLand - 0.4, "catch", { face: stage.face(-1) });
    stage.fly(tKick, tLand, punter, returner, 18);
    stage.hold(tLand, returner);
    if (kick.fair_catch) {
      returner.pose(tLand + 0.3, "stand");
      stage.moment(tLand, "catch", `Fair catch, ${returner.info.name}`);
      tEnd = tLand + 0.3;
    } else {
      stage.moment(tLand, "catch", `${returner.info.name} fields it`);
      returner.pose(tLand + 0.15, "carry");
      tEnd = returner.run(tLand + 0.15, stage.P(landU - kick.return, stage.inside(landV + stage.range(-6, 6))), 0.95);
      const end = returner.end;
      const gunner = [cover.role.G1, cover.role.G2].reduce((a, b) =>
        Math.abs(a.end.y - end.y) < Math.abs(b.end.y - end.y) ? a : b);
      gunner.pose(SNAP, "run").to(tEnd - 0.6, stage.toward(end, gunner.end, 3));
      tackle(stage, returner, [gunner], tEnd);
    }
  }
  const end = kick.touchback ? landing : returner.end;
  for (const actor of cover.actors.slice(1)) {
    if (stage.busy.has(actor)) continue;
    pursue(actor, SNAP + 0.3, end, tEnd + 0.3, actor.info.role.startsWith("G") ? 1.5 : stage.range(2, 8));
  }
  for (const actor of ret.actors.slice(1)) {
    actor.pose(SNAP, "run");
    if (actor.info.role.startsWith("R")) actor.run(SNAP, stage.P(-6, stage.v(actor.end) * 0.6), 0.8);
    pursue(actor, tKick, stage.P(stage.u(end) + 5, stage.v(actor.end) * 0.5), tEnd, 2);
  }
  return tEnd;
}

/** Field goals and extra points: snap, hold, and the kick through (or wide of) the uprights. */
function placeKick(stage: Stage, kicking: TeamSummary, blocking: TeamSummary, kickerId: number,
                   good: boolean, ballOn: number, label: string): number {
  const line = [-5.4, -3.6, -1.8, 1.8, 3.6, 5.4];
  const unit = kickUnit(stage, "offense", kicking, [
    { role: "K", u: -9.6, v: -1.8, prefs: ["K"], id: kickerId },
    { role: "H", u: -7, v: 0, prefs: ["P", "QB"], stance: "kneel" },
    { role: "LS", u: -0.7, v: 0, prefs: ["C", "OG"], stance: "stance3" },
    ...line.map((v, i) => ({ role: `L${i + 1}`, u: -0.9, v, prefs: LINE, stance: "stance3" as const })),
    { role: "W1", u: -1.6, v: -7, prefs: ["TE", "OT", "OLB"], stance: "stance2" },
    { role: "W2", u: -1.6, v: 7, prefs: ["TE", "OT", "OLB"], stance: "stance2" },
  ], 1);
  const block = kickUnit(stage, "defense", blocking, [
    ...[-6.4, -4.8, -3.2, -1.6, 0, 1.6, 3.2, 4.8, 6.4].map((v, i) => ({
      role: `B${i + 1}`, u: 1, v, prefs: RUSH, stance: "stance3" as const })),
    { role: "S1", u: 8, v: -6, prefs: BACKS },
    { role: "S2", u: 8, v: 6, prefs: BACKS },
  ], -1);
  const kicker = unit.role.K;
  const holder = unit.role.H;
  const tHold = SNAP + 0.4;
  const tKick = SNAP + 1.25;
  stage.rest(0, [stage.los, stage.ballY, BALL_REST]);
  stage.fly(SNAP, tHold, [stage.los, stage.ballY, 0.4], holder, 0.15);
  stage.hold(tHold, holder);
  stage.moment(SNAP, "snap", "Snap");
  kicker.pose(SNAP + 0.3, "run").hold(SNAP + 0.4).to(tKick, stage.P(-7.7, -0.5));
  kicker.pose(tKick - 0.2, "kick", { span: 0.4, face: stage.face(1) });
  // Through the uprights, or wide of them, and on into the net behind the end line.
  const post = 100 - ballOn + GOAL_POST_DEPTH;
  const beyond = post + 3;
  const atPost = good ? stage.range(-1.6, 1.6) : stage.pick([-1, 1]) * stage.range(3.6, 6);
  const end = stage.P(beyond, (atPost * (beyond + 7)) / (post + 7));
  const spot = stage.P(-7, 0);
  const flight = 1 + (post + 7) / 30;
  const tEnd = tKick + flight;
  stage.fly(tKick, tEnd, [spot.x, spot.y, 0.3], [end.x, end.y, 2.5], 6 + (post + 7) * 0.12);
  const ground: Vec3 = [end.x + stage.d, end.y, BALL_REST];
  stage.fly(tEnd, tEnd + 0.5, [end.x, end.y, 2.5], ground, 0.3);
  stage.rest(tEnd + 0.5, ground);
  stage.moment(tKick, "kick", `${kicker.info.name} kicks`);
  stage.moment(tEnd, "whistle", good ? `${label} is good!` : `${label} is no good`);
  if (good) kicker.pose(tEnd, "celebrate");
  for (const actor of [...unit.actors, ...block.actors]) {
    if (actor === kicker || actor === holder) continue;
    const toward = actor.info.side === "offense" ? 1 : -1;
    actor.pose(SNAP, "block", { face: stage.face(toward) });
    actor.run(SNAP, { x: actor.end.x + stage.d * toward * 0.5, y: actor.end.y }, 0.5);
    actor.pose(tEnd, "stand", { face: stage.face(toward) });
  }
  return tEnd;
}

/** The record only says whether a two-point try worked: show a quick throw into the end zone. */
function twoPoint(play: PlaybackPlay, stage: Stage, offenseTeam: TeamSummary,
                  defenseTeam: TeamSummary, good: boolean): number {
  const ours = new Picker(stage, offenseTeam.id);
  const theirs = new Picker(stage, defenseTeam.id);
  const offense = lineUp(stage, "offense", offenseTeam, offenseSpots(),
                         offenseSpots().map((s) => ours.pick([s.position])));
  const defense = lineUp(stage, "defense", defenseTeam, defenseSpots("base"),
                         defenseSpots("base").map((s) => theirs.pick([s.position])));
  const target = offense.role.TE;
  const qb = offense.role.QB.info.id;
  const tryPlay: PlaybackPlay = {
    ...play, ball_on: 98,
    events: [
      { t: "dropback", qb, depth: "short" },
      { t: "pass", qb, target: target.info.id, result: good ? "complete" : "incomplete", air: 4, yards: 4 },
    ],
    result: { type: "conversion", touchdown: good },
  };
  const tEnd = passPlay(scrimmageContext(stage, tryPlay, offense, defense, 98));
  for (const m of stage.moments) if (m.kind === "touchdown") m.text = "The two-point try is good!";
  if (!good) stage.moment(tEnd, "whistle", "The two-point try fails");
  return tEnd;
}

// ---------- the timeline ----------

function ballOnFor(play: PlaybackPlay): number {
  if (play.ball_on != null) return play.ball_on;
  if (find(play.events, "kickoff")) return 35;
  if (find(play.events, "extra_point")) return 85;
  if (find(play.events, "two_point")) return 98;
  return 25;
}

/** The timeline of one play, with the ball snapped `ballY` yards across the field. */
export function choreograph(play: PlaybackPlay, playback: GamePlayback,
                            ballY = WIDTH / 2): Choreography {
  const { home, away } = playback.game;
  const [offense, defense] = play.side === "home" ? [home, away] : [away, home];
  const d = driveDirection(play.quarter, play.side);
  const ballOn = ballOnFor(play);
  const events = play.events;
  const kickoffEvent = find(events, "kickoff");
  const puntEvent = find(events, "punt");
  const fg = find(events, "field_goal");
  const xp = find(events, "extra_point");
  const two = find(events, "two_point");
  const y = kickoffEvent || xp || two ? WIDTH / 2 : ballY;
  const roster = new Map(playback.players.map((p) => [p.id, p]));
  const stage = new Stage(mulberry32(playback.game.id * 1009 + play.n * 7919), d, fieldX(ballOn, d),
                          y, roster);

  let end: number;
  if (kickoffEvent) end = kickoff(play, stage, offense, defense);
  else if (puntEvent) end = punt(play, stage, offense, defense);
  else if (fg) end = placeKick(stage, offense, defense, fg.kicker, fg.good, ballOn, "The field goal");
  else if (xp) end = placeKick(stage, offense, defense, xp.kicker, xp.good, ballOn, "The extra point");
  else if (two) end = twoPoint(play, stage, offense, defense, two.good);
  else end = scrimmage(play, stage, offense, defense);

  // A flag for any foul, thrown near the offender.
  const penalty = find(events, "penalty");
  if (penalty) {
    const offender = stage.byId(penalty.player);
    const t = Math.min(end, SNAP + 0.4 + stage.rng() * Math.max(0, end - SNAP - 0.4));
    const at = offender ? offender.at(t) : stage.P(0, 0);
    stage.flag = { t, x: clampX(at.x + stage.range(-1, 1)), y: clampY(at.y + stage.range(-1, 1)) };
    stage.moment(t, "flag", `Flag: ${penalty.kind.replaceAll("_", " ")}`);
  }

  const duration = end + AFTER;
  stage.moment(end + 0.2, "whistle", "Whistle");
  const players = stage.actors.map((a) => a.toTimeline(duration));
  const timelineOf = new Map(stage.actors.map((a, i) => [a, players[i]]));
  const where = (p: Actor | Vec3, t: number): Vec3 =>
    p instanceof Actor ? handsAt(timelineOf.get(p)!, t) : p;
  const ball: BallSegment[] = stage.ball.map((step, i) => {
    const next = stage.ball[i + 1]?.from ?? duration;
    switch (step.kind) {
      case "held": return { kind: "held", from: step.from, to: next, player: step.player.info.id };
      case "rest": return { kind: "rest", from: step.from, to: next, at: step.at };
      case "flight": return { kind: "flight", from: step.from, to: step.to,
                              start: where(step.start, step.from), end: where(step.end, step.to),
                              apex: step.apex };
    }
  });

  // One whistle: the first (a touchback or a kick's result says more than "Whistle").
  const firstWhistle = stage.moments.find((m) => m.kind === "whistle");
  const moments = stage.moments
    .filter((m) => (m.kind !== "whistle" || m === firstWhistle) && m.t <= duration)
    .sort((a, b) => a.t - b.t);

  const last = ball[ball.length - 1];
  const finalY = last.kind === "held" ? endOf(players.find((p) => p.id === last.player)!).y
    : last.kind === "rest" ? last.at[1] : last.end[1];
  const restart = touchdown(play) || !!fg || !!xp || !!two || !!kickoffEvent?.touchback
    || !!puntEvent?.touchback;
  const nullified = !!penalty && play.result.type === "penalty";
  const timeline: PlayTimeline = {
    version: 1,
    duration,
    direction: d,
    los: kickoffEvent ? null : fieldX(ballOn, d),
    firstDownLine: play.down && play.distance && ballOn + play.distance < 100
      ? fieldX(ballOn + play.distance, d) : null,
    players,
    ball,
    moments,
    flag: stage.flag,
  };
  return { play, timeline, nextBallY: restart ? WIDTH / 2 : nullified ? y : hashSpot(finalY) };
}

function endOf(player: TimelinePlayer): Point {
  const last = player.path[player.path.length - 1];
  return { x: last.x, y: last.y };
}
