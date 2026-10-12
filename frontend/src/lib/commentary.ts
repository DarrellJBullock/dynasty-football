/**
 * The commentary team (docs/design/sound.md §4): a play-by-play announcer who calls each
 * play as it happens, and an analyst who adds a line after it when there's something to
 * say. Written from the play's events (like the play-by-play text and the stat overlays),
 * timed to its moments, and phrased deterministically: the same play is always called the
 * same way. Pronoun-neutral throughout (leagues can be men's or women's). Pure.
 */

import type { PlayTimeline } from "@/components/field/playback/timeline";
import { breakAfter, driveEndingAt, statLowerThird } from "@/lib/gameStats";
import { formatSpot } from "@/lib/games";
import { penaltyName } from "@/lib/penalties";
import type { GamePlayback, PlaybackPlay, PlaybackPlayer, PlayEvent } from "@/lib/types";

export type Voice = "play" | "color";
export interface CommentaryLine { t: number; voice: Voice; text: string }

type Event<T extends PlayEvent["t"]> = Extract<PlayEvent, { t: T }>;

/** The lines for play `index` of the game, in time order. */
export function commentaryFor(playback: GamePlayback, index: number, timeline: PlayTimeline): CommentaryLine[] {
  const play = playback.plays[index];
  if (!play) return [];
  const roster = new Map(playback.players.map((p) => [p.id, p]));
  const c = new Caller(playback, play, timeline, roster);
  c.call();
  c.analyze(index);
  return c.lines.sort((a, b) => a.t - b.t);
}

/** Which caption shows at `t`: the latest line that's started, for a few seconds. */
export function captionAt(lines: CommentaryLine[], t: number, hold = 3.5): CommentaryLine | null {
  let current: CommentaryLine | null = null;
  for (const line of lines) if (line.t <= t) current = line;
  return current && t - current.t <= hold ? current : null;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

class Caller {
  readonly lines: CommentaryLine[] = [];
  private readonly key: number; // picks phrasings: the same play reads the same every time

  constructor(private readonly playback: GamePlayback, private readonly play: PlaybackPlay,
              private readonly timeline: PlayTimeline, private readonly roster: Map<number, PlaybackPlayer>) {
    this.key = Math.abs(playback.game.id * 7919 + play.n * 104729);
  }

  // ---------- helpers ----------

  private at(kind: string): number | null {
    return this.timeline.moments.find((m) => m.kind === kind)?.t ?? null;
  }

  private get end(): number {
    return this.at("whistle") ?? this.timeline.duration;
  }

  private say(t: number | null, voice: Voice, text: string) {
    if (t !== null) this.lines.push({ t: Math.max(0, Math.min(t, this.timeline.duration)), voice, text });
  }

  private pick(options: string[], salt = 0): string {
    return options[(this.key + salt) % options.length];
  }

  /** A player as announcers say them: the last name ("a teammate" for stand-ins). */
  private name(id: number | null | undefined): string {
    const player = id != null ? this.roster.get(id) : undefined;
    return player ? player.name.split(" ").slice(-1)[0] : "a teammate";
  }

  private event<T extends PlayEvent["t"]>(t: T): Event<T> | undefined {
    return this.play.events.find((e) => e.t === t) as Event<T> | undefined;
  }

  private get teams() {
    const { home, away } = this.playback.game;
    return this.play.side === "home" ? { offense: home, defense: away } : { offense: away, defense: home };
  }

  /** "the HFD 30": where a play that gained `yards` from the line ended. */
  private spot(yards: number): string {
    const from = this.play.ball_on ?? 25;
    const ballOn = Math.max(1, Math.min(99, from + yards));
    const { offense, defense } = this.teams;
    const label = formatSpot(ballOn, offense.abbreviation, defense.abbreviation);
    return label === "50" ? "midfield" : `the ${label}`;
  }

  private tacklers(): string | null {
    const by = this.event("tackle")?.by ?? [];
    if (!by.length) return null;
    return by.length > 1 ? `${this.name(by[0])} and ${this.name(by[1])}` : this.name(by[0]);
  }

  // ---------- the play-by-play ----------

  call() {
    const ev = (t: PlayEvent["t"]) => this.play.events.some((e) => e.t === t);
    if (ev("kickoff")) return this.kickoff();
    if (ev("punt")) return this.punt();
    if (ev("field_goal") || ev("extra_point")) return this.kick();
    if (ev("two_point")) return this.twoPoint();
    if (this.play.result.type === "penalty" && this.play.events.every((e) => e.t === "penalty")) {
      return this.preSnapFoul();
    }
    if (ev("kneel")) return this.say(this.at("snap"), "play", `${this.name(this.event("kneel")!.qb)} takes a knee.`);
    if (ev("sack")) this.sack();
    else if (ev("pass")) this.pass();
    else if (ev("scramble")) this.scramble();
    else if (ev("rush")) this.run();
    this.fumble();
    this.flag();
    this.touchdown();
  }

  private run() {
    const rush = this.event("rush")!;
    const handoff = this.event("handoff");
    const runner = this.name(rush.player);
    this.say(this.at("handoff") ?? this.at("snap"), "play", handoff?.direction === "outside"
      ? this.pick([`Pitch to ${runner}, headed for the edge…`, `${runner} takes it outside…`])
      : this.pick([`Handoff to ${runner}…`, `${runner} up the middle…`, `Give to ${runner}…`]));
    if (this.play.result.touchdown || this.event("fumble")) return;
    const by = this.tacklers();
    const gain = rush.yards;
    const result = gain > 0
      ? this.pick([`picks up ${plural(gain, "yard")}`, `gains ${gain}`, `gets ${gain}`], 1)
      : gain === 0 ? "no gain" : `stopped for a loss of ${-gain}`;
    this.say(this.at("tackle") ?? this.end, "play",
      `${result.charAt(0).toUpperCase()}${result.slice(1)}${by ? `, brought down by ${by}` : ""}${this.firstDown()}.`);
  }

  private pass() {
    const pass = this.event("pass")!;
    const qb = this.name(pass.qb);
    const target = this.name(pass.target);
    this.say(this.at("snap"), "play", this.pick([`${qb} drops back…`, `${qb} back to throw…`,
                                                 `${qb} in the pocket…`]));
    const thrown = this.at("throw") ?? this.at("snap");
    if (pass.result === "throwaway") return this.say(thrown, "play", `${qb} has to throw it away.`);
    if (pass.result === "interception") {
      const pick = this.event("interception")!;
      this.say(thrown, "play", `Looking for ${target}…`);
      return this.say(this.at("turnover") ?? this.at("catch") ?? this.end, "play",
        `Intercepted! ${this.name(pick.by)} picks it off${pick.return > 0 ? ` and brings it back ${pick.return}` : ""}!`);
    }
    if (pass.result === "incomplete") {
      const defended = this.event("pass_defended");
      return this.say(thrown, "play", defended
        ? `For ${target}… broken up by ${this.name(defended.by)}!`
        : this.pick([`For ${target}… incomplete.`, `Looking for ${target}, and it falls incomplete.`]));
    }
    this.say(thrown, "play", this.pick([`Fires for ${target}…`, `Throws to ${target}…`,
                                        `Looking for ${target}…`], 2));
    if (this.play.result.touchdown || this.event("fumble")) return;
    const by = this.tacklers();
    this.say(this.at("catch"), "play", `Caught at ${this.spot(pass.air)}!`);
    this.say(this.at("tackle") ?? this.end, "play",
      `${by ? `${target} brought down by ${by}` : `${target} is down`} after a gain of ${pass.yards}${this.firstDown()}.`);
  }

  private sack() {
    const sack = this.event("sack")!;
    this.say(this.at("snap"), "play", `${this.name(sack.qb)} drops back…`);
    this.say(this.at("tackle") ?? this.end, "play", this.pick([
      `Sacked! ${this.name(sack.by)} gets there for a loss of ${-sack.yards}.`,
      `Taken down! ${this.name(sack.by)} with the sack.`,
    ]));
  }

  private scramble() {
    const run = this.event("scramble")!;
    this.say(this.at("snap"), "play", `${this.name(run.qb)} looks… and takes off!`);
    if (this.play.result.touchdown) return;
    this.say(this.at("tackle") ?? this.end, "play", `${this.name(run.qb)} scrambles for ${plural(run.yards, "yard")}${this.firstDown()}.`);
  }

  private firstDown(): string {
    return this.play.result.first_down && this.play.result.type !== "penalty" ? ", and that's a first down" : "";
  }

  private fumble() {
    const fumble = this.event("fumble");
    if (!fumble) return;
    this.say(this.at("turnover") ?? this.at("tackle") ?? this.end, "play", fumble.lost
      ? `Fumble! ${this.name(fumble.forced_by)} knocks it loose, and the defense has it!`
      : `It's on the ground! ${this.name(fumble.forced_by)} jars it loose… but the offense hangs on.`);
  }

  private touchdown() {
    if (!this.play.result.touchdown && !this.play.result.defensive_td) return;
    const team = this.play.result.defensive_td ? this.teams.defense : this.teams.offense;
    this.say(this.at("touchdown") ?? this.end, "play", this.pick([
      `Touchdown, ${team.nickname}!`, `In for the score! Touchdown ${team.nickname}!`, `Into the end zone! Touchdown!`,
    ], 3));
  }

  private flag() {
    if (this.event("penalty")) this.say(this.at("flag"), "play", "And there's a flag on the play.");
  }

  private preSnapFoul() {
    const foul = this.event("penalty")!;
    this.say(this.at("flag") ?? this.at("snap") ?? 0.5, "play",
      `Flag before the snap: ${penaltyName(foul.kind).toLowerCase()}, ${foul.team}. ${plural(foul.yards, "yard")}.`);
  }

  private kickoff() {
    const kick = this.event("kickoff")!;
    const kicker = this.name(kick.kicker);
    this.say(this.at("kick"), "play", kick.kind === "onside" ? `${kicker} tries the onside kick!`
      : kick.kind === "squib" ? `${kicker} squibs it.` : this.pick([`${kicker} kicks it away.`, `Here's the kick from ${kicker}.`]));
    if (kick.kind === "onside") {
      return this.say(this.end, "play", kick.recovered ? "And the kicking team recovers it! What a gamble!"
        : "And the receiving team covers it up.");
    }
    if (kick.touchback) return this.say(this.end, "play", "Into the end zone. Touchback.");
    this.say(this.at("tackle") ?? this.end, "play",
      `${this.name(kick.returner)} brings it back ${plural(kick.return, "yard")}.`);
  }

  private punt() {
    const punt = this.event("punt")!;
    this.say(this.at("kick"), "play", `${this.name(punt.punter)} punts it away.`);
    this.say(this.at("tackle") ?? this.end, "play", punt.touchback ? "It bounces into the end zone. Touchback."
      : punt.fair_catch ? `${this.name(punt.returner)} calls for the fair catch.`
      : `${this.name(punt.returner)} returns it ${plural(punt.return, "yard")}.`);
  }

  private kick() {
    const fg = this.event("field_goal");
    const xp = this.event("extra_point");
    const kicker = this.name(fg?.kicker ?? xp?.kicker);
    const good = fg ? fg.good : xp!.good;
    this.say(this.at("kick"), "play", fg ? `${kicker} lines up from ${fg.distance}…` : `The extra point from ${kicker}…`);
    this.say(this.end, "play", good ? this.pick(["It's good!", "Right down the middle. It's good!"], 4)
      : this.pick(["No good!", "It's wide!"], 4));
  }

  private twoPoint() {
    const tryIt = this.event("two_point")!;
    this.say(this.at("snap"), "play", `They're going for two…`);
    this.say(this.end, "play", tryIt.good ? "And they get it! The two-point try is good!" : "Stopped! The try fails.");
  }

  // ---------- the analyst ----------

  /** One line after the play, if there's something worth saying, in this order. */
  analyze(index: number) {
    const after = Math.min(this.timeline.duration, this.end + 0.8);
    const plays = this.playback.plays;
    const injury = this.event("injury");
    if (injury) {
      return this.say(after, "color",
        `${this.name(injury.player)} is slow to get up… looks like ${injury.injury.toLowerCase()}. That's a big loss for ${injury.team}.`);
    }
    const foul = this.event("penalty");
    if (foul && this.play.events.some((e) => e.t !== "penalty")) {
      const name = penaltyName(foul.kind).toLowerCase();
      return this.say(after, "color", this.play.result.nullified
        ? `That's ${name} on ${foul.team}. ${foul.yards} yards, and the play comes back.`
        : `${name.charAt(0).toUpperCase()}${name.slice(1)} on ${foul.team}, ${foul.yards} yards${foul.automatic_first ? " and a first down" : ""}.`);
    }
    const pause = breakAfter(plays, index);
    if (pause) {
      const { home, away } = this.playback.game;
      const { score } = this.play;
      return this.say(after, "color", pause === "final"
        ? `And that's the ball game. ${home.nickname} ${score.home}, ${away.nickname} ${score.away}.`
        : `That'll do it for the first half. ${home.nickname} ${score.home}, ${away.nickname} ${score.away}.`);
    }
    const drive = driveEndingAt(plays, index);
    if (drive && drive.plays >= 4 && drive.result !== "Punt") {
      return this.say(after, "color",
        `What a drive: ${plural(drive.plays, "play")}, ${plural(drive.yards, "yard")}, ending in a ${drive.result.toLowerCase()}.`);
    }
    const stat = statLowerThird(plays, index, this.roster);
    if (stat?.line) {
      return this.say(after, "color", this.pick([
        `${this.name(stat.id)} is having a day: ${stat.line}.`, `That's ${stat.line} for ${this.name(stat.id)} now.`,
      ], 5));
    }
    const next = plays[index + 1];
    if (next && next.down === 4 && next.side === this.play.side && (next.distance ?? 99) <= 2) {
      this.say(after, "color", `That sets up fourth and ${next.distance}. Decision time.`);
    }
  }
}
