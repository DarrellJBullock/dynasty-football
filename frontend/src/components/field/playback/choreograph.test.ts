import { describe, expect, it } from "vitest";
import type { PlaybackPlay, PlayEvent } from "@/lib/types";
import { makePlay, makePlayback, opponent, pid, team } from "@/test/fixtures";
import { fieldX, GOALPOST, HASH_INSET, LENGTH, WIDTH } from "../layout";
import { choreograph, choreographGame, driveDirection, hashSpot, SNAP } from "./choreograph";
import { anglesAt, ballAt, handsAt, positionAt, type PlayTimeline } from "./timeline";

const H = team.id;
const A = opponent.id;

const kickPlay = (events: PlayEvent[], overrides: Partial<PlaybackPlay> = {}) =>
  makePlay({ down: null, distance: null, ball_on: null, defense: null, personnel: null, events,
             result: { type: events[0].t }, ...overrides });

const PLAYS: Record<string, PlaybackPlay> = {
  run: makePlay({
    result: { type: "run", yards: 6 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
             { t: "rush", player: pid(H, "RB"), yards: 6 }, { t: "tackle", by: [pid(A, "MLB")] }],
  }),
  outsideTouchdown: makePlay({
    ball_on: 88, result: { type: "run", yards: 12, touchdown: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "outside" },
             { t: "rush", player: pid(H, "RB"), yards: 12 }],
  }),
  stuffed: makePlay({
    result: { type: "run", yards: -3 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
             { t: "rush", player: pid(H, "RB"), yards: -3 }, { t: "tackle", by: [pid(A, "DT")] }],
  }),
  complete: makePlay({
    defense: { package: "nickel", coverage: "man", blitz: true },
    personnel: undefined, result: { type: "pass", yards: 14, result: "complete" },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "short" }, { t: "pressure" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR"), result: "complete", air: 8, yards: 14 },
             { t: "tackle", by: [pid(A, "CB")] }],
  }),
  defended: makePlay({
    result: { type: "pass", yards: 0, result: "incomplete" },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "deep" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR", 1), result: "incomplete", air: 30, yards: 0 },
             { t: "pass_defended", by: pid(A, "CB", 1) }],
  }),
  interception: makePlay({
    result: { type: "pass", yards: 0, result: "interception", turnover: true },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "TE"), result: "interception", air: 15, yards: 0 },
             { t: "interception", by: pid(A, "FS"), return: 12 }],
  }),
  throwaway: makePlay({
    result: { type: "pass", yards: 0, result: "throwaway" },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "pass", qb: pid(H, "QB"), target: null, result: "throwaway", air: 0, yards: 0 }],
  }),
  sackFumble: makePlay({
    result: { type: "sack", yards: -7, turnover: true },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "sack", qb: pid(H, "QB"), by: pid(A, "DE"), yards: -7 },
             { t: "fumble", player: pid(H, "QB"), forced_by: pid(A, "DE"), lost: true }],
  }),
  scramble: makePlay({
    result: { type: "scramble", yards: 9 },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "scramble", qb: pid(H, "QB"), yards: 9 }, { t: "tackle", by: [pid(A, "MLB")] }],
  }),
  kneel: makePlay({
    result: { type: "kneel", yards: -1 }, events: [{ t: "kneel", qb: pid(H, "QB"), yards: -1 }],
  }),
  falseStart: makePlay({
    result: { type: "penalty" },
    events: [{ t: "penalty", team: "HFD", kind: "false_start", yards: 5, player: pid(H, "OG"),
               automatic_first: false }],
  }),
  heldRun: makePlay({
    quarter: 2, result: { type: "penalty", nullified: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
             { t: "rush", player: pid(H, "RB"), yards: 11 }, { t: "tackle", by: [pid(A, "SS")] },
             { t: "penalty", team: "offense", kind: "holding", yards: 10, player: pid(H, "OT"),
               automatic_first: false }],
  }),
  kickoffReturn: kickPlay([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 27,
                             returner: pid(H, "WR", 2) }], { side: "away", offense: "ABQ" }),
  squibKick: kickPlay([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 31, kind: "squib",
                         returner: pid(H, "RB") }], { side: "away", offense: "ABQ" }),
  onsideRecovered: kickPlay([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 54, kind: "onside",
                               recovered: true, recovered_by: pid(A, "WR", 1) }], { side: "away", offense: "ABQ" }),
  onsideLost: kickPlay([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 53, kind: "onside",
                          recovered: false, recovered_by: pid(H, "TE") }], { side: "away", offense: "ABQ" }),
  kickoffTouchback: kickPlay([{ t: "kickoff", kicker: pid(A, "K"), touchback: true, return: 0 }],
                             { side: "away", offense: "ABQ" }),
  puntReturn: kickPlay([{ t: "punt", punter: pid(H, "P"), yards: 45, touchback: false, fair_catch: false,
                          return: 8, returner: pid(A, "WR") }], { down: 4, distance: 6, ball_on: 40 }),
  fairCatch: kickPlay([{ t: "punt", punter: pid(H, "P"), yards: 44, touchback: false, fair_catch: true,
                         return: 0, returner: pid(A, "WR") }], { down: 4, distance: 6, ball_on: 44 }),
  puntTouchback: kickPlay([{ t: "punt", punter: pid(H, "P"), yards: 38, touchback: true, fair_catch: false,
                             return: 0 }], { down: 4, distance: 9, ball_on: 62 }),
  fieldGoal: kickPlay([{ t: "field_goal", kicker: pid(H, "K"), distance: 42, good: true }],
                      { down: 4, distance: 3, ball_on: 75 }),
  missedFieldGoal: kickPlay([{ t: "field_goal", kicker: pid(H, "K"), distance: 50, good: false }],
                            { down: 4, distance: 3, ball_on: 67 }),
  extraPoint: kickPlay([{ t: "extra_point", kicker: pid(H, "K"), good: true }]),
  twoPoint: kickPlay([{ t: "two_point", good: true }]),
};

const playback = makePlayback(Object.values(PLAYS));
const choreographed = choreographGame(playback);
const byName = Object.fromEntries(Object.keys(PLAYS).map((name, i) => [name, choreographed[i]]));

function ballEnd(timeline: PlayTimeline) {
  const players = new Map(timeline.players.map((p) => [p.id, p]));
  return ballAt(timeline, timeline.duration, (id, t) => handsAt(players.get(id)!, t));
}

function player(timeline: PlayTimeline, id: number) {
  const found = timeline.players.find((p) => p.id === id);
  if (!found) throw new Error(`player ${id} not on the field`);
  return found;
}

describe("choreograph: every play", () => {
  it.each(Object.keys(PLAYS))("%s puts 22 players on the field, in bounds, in order", (name) => {
    const { timeline } = byName[name];
    expect(timeline.players).toHaveLength(22);
    expect(timeline.players.filter((p) => p.side === "offense")).toHaveLength(11);
    expect(new Set(timeline.players.map((p) => `${p.side}-${p.role}`)).size).toBe(22);
    for (const p of timeline.players) {
      for (let i = 0; i < p.path.length; i++) {
        const k = p.path[i];
        expect(k.y).toBeGreaterThanOrEqual(0);
        expect(k.y).toBeLessThanOrEqual(WIDTH);
        expect(k.x).toBeGreaterThanOrEqual(0);
        expect(k.x).toBeLessThanOrEqual(LENGTH);
        if (i > 0) expect(k.t).toBeGreaterThan(p.path[i - 1].t);
      }
      expect(p.poses[0].t).toBe(0);
      expect(p.path[p.path.length - 1].t).toBeCloseTo(timeline.duration);
    }
    expect(timeline.duration).toBeGreaterThan(SNAP);
    expect(timeline.duration).toBeLessThan(16);
  });

  it.each(Object.keys(PLAYS))("%s has ordered moments and a ball for the whole play", (name) => {
    const { timeline } = byName[name];
    const times = timeline.moments.map((m) => m.t);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(times.every((t) => t >= 0 && t <= timeline.duration)).toBe(true);
    expect(timeline.moments.filter((m) => m.kind === "whistle")).toHaveLength(1);
    expect(timeline.ball[0].from).toBe(0);
    for (let i = 1; i < timeline.ball.length; i++) {
      expect(timeline.ball[i].from).toBeCloseTo(timeline.ball[i - 1].to);
    }
    for (let t = 0; t <= timeline.duration; t += 0.25) {
      expect(ballEnd({ ...timeline, duration: t }).every(Number.isFinite)).toBe(true);
    }
  });

  it("is deterministic", () => {
    expect(choreographGame(playback)).toEqual(choreographed);
  });

  it("spots each snap where the last play ended, between the hashes", () => {
    for (const { nextBallY } of choreographed) {
      expect(nextBallY).toBeGreaterThanOrEqual(HASH_INSET);
      expect(nextBallY).toBeLessThanOrEqual(WIDTH - HASH_INSET);
    }
    expect(hashSpot(2)).toBe(HASH_INSET);
    expect(hashSpot(WIDTH / 2)).toBe(WIDTH / 2);
    // Scores and touchbacks restart in the middle.
    expect(byName.outsideTouchdown.nextBallY).toBe(WIDTH / 2);
    expect(byName.kickoffTouchback.nextBallY).toBe(WIDTH / 2);
  });

  it("switches ends every quarter", () => {
    expect(driveDirection(1, "home")).toBe(1);
    expect(driveDirection(1, "away")).toBe(-1);
    expect(driveDirection(2, "home")).toBe(-1);
    expect(driveDirection(4, "away")).toBe(1);
    expect(byName.heldRun.timeline.direction).toBe(-1);
    expect(byName.heldRun.timeline.los).toBe(fieldX(30, -1));
  });
});

describe("choreograph: the record decides where the play ends", () => {
  it.each([["run", 6], ["stuffed", -3], ["complete", 14], ["scramble", 9], ["kneel", -1]] as const)(
    "%s ends with the ball at the recorded spot", (name, yards) => {
      const { timeline } = byName[name];
      expect(ballEnd(timeline)[0]).toBeCloseTo(fieldX(30 + yards, 1), -0.2); // within ~0.8 yd
    });

  it("a touchdown crosses the goal line and celebrates", () => {
    const { timeline } = byName.outsideTouchdown;
    expect(ballEnd(timeline)[0]).toBeGreaterThan(fieldX(100, 1));
    const rb = player(timeline, pid(H, "RB"));
    expect(rb.poses.at(-1)!.pose).toBe("celebrate");
    expect(timeline.moments.map((m) => m.kind)).toContain("touchdown");
  });

  it.each(["run", "complete", "scramble"])("%s: the recorded tackler meets the carrier", (name) => {
    const { timeline, play } = byName[name];
    const tackle = timeline.moments.find((m) => m.kind === "tackle")!;
    const carrierId = name === "complete" ? pid(H, "WR") : name === "run" ? pid(H, "RB") : pid(H, "QB");
    const tacklerId = (play.events.find((e) => e.t === "tackle") as { by: number[] }).by[0];
    const t = tackle.t + 0.1;
    const a = positionAt(player(timeline, carrierId).path, t);
    const b = positionAt(player(timeline, tacklerId).path, t);
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(1.2);
    expect(anglesAt(player(timeline, carrierId), t + 0.5).lie).toBe(1);
  });

  it("a sack brings the QB down at the recorded spot and the defense falls on the fumble", () => {
    const { timeline } = byName.sackFumble;
    const qb = player(timeline, pid(H, "QB"));
    const sack = timeline.moments.find((m) => m.text.startsWith("Sacked by"))!;
    expect(positionAt(qb.path, sack.t).x).toBeCloseTo(fieldX(23, 1), -0.2);
    const last = timeline.ball.at(-1)!;
    expect(last).toMatchObject({ kind: "held", player: pid(A, "DE") });
    expect(timeline.moments.map((m) => m.kind)).toContain("turnover");
  });

  it("passes are thrown and caught, broken up, or picked off", () => {
    const complete = byName.complete.timeline;
    const qb = player(complete, pid(H, "QB"));
    expect(qb.poses.map((p) => p.pose)).toContain("throw");
    expect(complete.ball.map((b) => b.kind)).toEqual(["rest", "held", "flight", "held"]);
    expect(complete.moments.map((m) => m.kind)).toEqual(
      expect.arrayContaining(["snap", "throw", "catch", "tackle", "whistle"]));

    const defended = byName.defended.timeline;
    expect(defended.ball.at(-1)!.kind).toBe("rest"); // on the ground
    expect(player(defended, pid(A, "CB", 1)).poses.map((p) => p.pose)).toContain("dive");

    const picked = byName.interception.timeline;
    expect(picked.ball.at(-1)).toMatchObject({ kind: "held", player: pid(A, "FS") });
    // Caught 15 yards downfield, returned 12 back toward the line.
    expect(ballEnd(picked)[0]).toBeCloseTo(fieldX(30 + 15 - 12, 1), -0.3);

    const away = byName.throwaway.timeline.ball.at(-1)!;
    expect(away.kind === "rest" && (away.at[1] < 0 || away.at[1] > WIDTH)).toBe(true);
  });

  it("a false start: the lineman flinches, the flag flies, nobody snaps the ball", () => {
    const { timeline } = byName.falseStart;
    expect(timeline.flag).not.toBeNull();
    expect(timeline.moments.map((m) => m.kind)).not.toContain("snap");
    const guard = player(timeline, pid(H, "OG"));
    expect(positionAt(guard.path, timeline.duration).x).toBeGreaterThan(guard.path[0].x);
    expect(timeline.ball).toHaveLength(1);
  });

  it("a nullified play still plays out, with a flag", () => {
    const { timeline } = byName.heldRun;
    expect(timeline.flag).not.toBeNull();
    expect(timeline.moments.find((m) => m.kind === "flag")!.text).toBe("Flag: holding");
    expect(timeline.moments.map((m) => m.kind)).toContain("tackle");
  });
});

describe("choreograph: kicks", () => {
  it("kickoff returns end at the recorded spot; touchbacks take a knee", () => {
    // ABQ kicks in the 1st quarter, so HFD returns toward +x from its own goal line at x 10.
    const ret = byName.kickoffReturn.timeline;
    expect(ret.los).toBeNull();
    expect(ballEnd(ret)[0]).toBeCloseTo(fieldX(27, 1), -0.2);
    expect(player(ret, pid(H, "WR", 2)).role).toBe("KR");
    expect(player(ret, pid(A, "K")).poses.map((p) => p.pose)).toContain("kick");

    const touchback = byName.kickoffTouchback.timeline;
    expect(touchback.moments.map((m) => m.text)).toContain("Touchback");
    expect(touchback.players.find((p) => p.role === "KR")!.poses.at(-1)!.pose).toBe("kneel");
  });

  it("squibs bounce short and are returned to the recorded spot", () => {
    const { timeline } = byName.squibKick;
    expect(ballEnd(timeline)[0]).toBeCloseTo(fieldX(31, 1), -0.2);
    const flights = timeline.ball.filter((b) => b.kind === "flight");
    expect(flights.length).toBeGreaterThanOrEqual(2); // the kick, then the skip to the returner
    expect(timeline.moments.map((m) => m.text)).toContain("H. RB1 fields the squib");
  });

  it("onside kicks end with the recorded recoverer on the ball, 10–13 yards out", () => {
    // ABQ kicks toward −x from its 35 (field x 75); the ball is recovered 11–12 yards on.
    for (const [name, id, team] of [["onsideRecovered", pid(A, "WR", 1), "the kicking team!"],
                                    ["onsideLost", pid(H, "TE"), "the receiving team"]] as const) {
      const { timeline } = byName[name];
      const last = timeline.ball.at(-1)!;
      expect(last).toMatchObject({ kind: "held", player: id });
      expect(ballEnd(timeline)[0]).toBeCloseTo(fieldX(name === "onsideRecovered" ? 54 : 53, 1), -0.3);
      expect(timeline.moments.some((m) => m.text.endsWith(team))).toBe(true);
      expect(player(timeline, id).poses.map((p) => p.pose)).toContain("dive");
    }
  });

  it("punts: returned to the recorded spot, fair caught, or into the end zone", () => {
    const ret = byName.puntReturn.timeline;
    // HFD punts from its 40: 45 yards to ABQ's 15, returned 8 to ABQ's 23 (HFD's 77).
    expect(ballEnd(ret)[0]).toBeCloseTo(fieldX(77, 1), -0.2);
    expect(player(ret, pid(H, "P")).poses.map((p) => p.pose)).toContain("kick");
    expect(byName.fairCatch.timeline.moments.map((m) => m.text)).toContain("Fair catch, A. WR2");
    expect(ballEnd(byName.puntTouchback.timeline)[0]).toBeGreaterThan(fieldX(100, 1));
  });

  it("field goals split the uprights or miss wide", () => {
    for (const [name, good] of [["fieldGoal", true], ["missedFieldGoal", false]] as const) {
      const { timeline } = byName[name];
      const players = new Map(timeline.players.map((p) => [p.id, p]));
      const flight = timeline.ball.find((b) => b.kind === "flight" && b.end[0] > 100)!;
      // Find where the ball crosses the plane of the goal posts (the end line, x = 120).
      let crossing: number[] | null = null;
      for (let t = flight.from; t <= flight.to; t += 0.01) {
        const ball = ballAt(timeline, t, (id, at) => handsAt(players.get(id)!, at));
        if (ball[0] >= LENGTH) { crossing = ball; break; }
      }
      expect(crossing).not.toBeNull();
      const [, y, z] = crossing!;
      expect(z).toBeGreaterThan(GOALPOST.crossbar);
      expect(Math.abs(y - WIDTH / 2) < GOALPOST.width / 2).toBe(good);
      expect(timeline.moments.some((m) => m.text === (good ? "The field goal is good!" : "The field goal is no good"))).toBe(true);
    }
  });

  it("conversions line up at the 15 or the 2", () => {
    expect(byName.extraPoint.timeline.los).toBe(fieldX(85, 1));
    const two = byName.twoPoint.timeline;
    expect(two.los).toBe(fieldX(98, 1));
    expect(ballEnd(two)[0]).toBeGreaterThan(fieldX(100, 1));
    expect(two.moments.map((m) => m.text)).toContain("The two-point try is good!");
  });

  it("fills kick units from the team, then stand-ins", () => {
    const { timeline } = choreograph(PLAYS.kickoffReturn, { ...playback, players: [] });
    expect(timeline.players).toHaveLength(22);
    expect(timeline.players.every((p) => p.name === "Stand-in")).toBe(true);
    expect(new Set(timeline.players.map((p) => p.id)).size).toBe(22);
  });
});
