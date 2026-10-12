import { describe, expect, it } from "vitest";
import { choreographGame } from "@/components/field/playback/choreograph";
import type { PlaybackPlay, PlayEvent } from "@/lib/types";
import { makePlay, makePlayback, opponent, pid, team } from "@/test/fixtures";
import { crowdLevel, dueCues, reaction, soundCues, type SoundCue } from "./cues";

const H = team.id;
const A = opponent.id;
const HOME = { neutral_site: false };

const kick = (events: PlayEvent[], overrides: Partial<PlaybackPlay> = {}) =>
  makePlay({ down: null, distance: null, ball_on: null, defense: null, personnel: null, events,
             result: { type: events[0].t }, ...overrides });

const PLAYS: Record<string, PlaybackPlay> = {
  run: makePlay({ result: { type: "run", yards: 4 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" }, { t: "rush", player: pid(H, "RB"), yards: 4 },
             { t: "tackle", by: [pid(A, "MLB")] }] }),
  homeTouchdown: makePlay({ ball_on: 70, result: { type: "run", yards: 30, touchdown: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "outside" }, { t: "rush", player: pid(H, "RB"), yards: 30 }] }),
  awayTouchdown: makePlay({ side: "away", ball_on: 70, result: { type: "run", yards: 30, touchdown: true },
    events: [{ t: "handoff", to: pid(A, "RB"), direction: "outside" }, { t: "rush", player: pid(A, "RB"), yards: 30 }] }),
  sackOfVisitors: makePlay({ side: "away", result: { type: "sack", yards: -7 },
    events: [{ t: "dropback", qb: pid(A, "QB"), depth: "medium" }, { t: "sack", qb: pid(A, "QB"), by: pid(H, "DE"), yards: -7 }] }),
  kickoff: kick([{ t: "kickoff", kicker: pid(H, "K"), touchback: false, return: 22, returner: pid(A, "WR") }]),
  fieldGoal: kick([{ t: "field_goal", kicker: pid(H, "K"), distance: 42, good: true }], { down: 4, distance: 3, ball_on: 75 }),
  missedFieldGoal: kick([{ t: "field_goal", kicker: pid(H, "K"), distance: 52, good: false }], { down: 4, distance: 3, ball_on: 65 }),
  falseStart: makePlay({ result: { type: "penalty" },
    events: [{ t: "penalty", team: team.abbreviation, kind: "false_start", yards: 5, player: pid(H, "OT"), automatic_first: false }] }),
};
const playback = makePlayback(Object.values(PLAYS));
const timelines = Object.fromEntries(Object.keys(PLAYS).map((name, i) => [name, choreographGame(playback)[i].timeline]));
const cues = (name: string, game = HOME) => soundCues(PLAYS[name], timelines[name], game);
const names = (list: SoundCue[]) => list.map((c) => c.sound);

describe("a play's sounds", () => {
  it("calls the signals, snaps, hits and whistles a run in order", () => {
    const run = cues("run");
    expect(names(run)).toEqual(expect.arrayContaining(["cadence", "snap", "hit", "whistle"]));
    const at = (sound: string) => run.find((c) => c.sound === sound)!.t;
    expect(at("cadence")).toBeLessThan(at("snap"));
    expect(at("snap")).toBeLessThan(at("whistle"));
    expect(run.every((c) => c.t >= 0 && c.t <= timelines.run.duration)).toBe(true);
    expect(run.some((c) => c.reaction)).toBe(false); // a 4-yard run: nothing to react to
    expect(run.map((c) => c.t)).toEqual([...run.map((c) => c.t)].sort((a, b) => a - b));
  });

  it("has the home crowd cheer its team's touchdown and groan at the visitors'", () => {
    const home = cues("homeTouchdown");
    expect(names(home)).toEqual(expect.arrayContaining(["swell", "cheer"]));
    expect(names(home)).not.toContain("groan");
    const swell = home.find((c) => c.sound === "swell")!;
    expect(swell.duration).toBeGreaterThan(0.6);
    expect(names(cues("awayTouchdown"))).toContain("groan");
    expect(names(cues("awayTouchdown"))).not.toContain("cheer");
  });

  it("splits the difference at a neutral site", () => {
    const neutral = cues("awayTouchdown", { neutral_site: true });
    const cheer = neutral.find((c) => c.sound === "cheer")!;
    expect(cheer.gain).toBeLessThan(cues("homeTouchdown").find((c) => c.sound === "cheer")!.gain);
    expect(names(neutral)).not.toContain("groan");
  });

  it("makes a sack of the visitors a big hit the home crowd likes", () => {
    const sack = cues("sackOfVisitors");
    expect(names(sack)).toContain("bigHit");
    expect(names(sack)).toContain("cheer");
    expect(reaction(PLAYS.sackOfVisitors)).toEqual({ side: "home", big: false });
  });

  it("thumps the kicks, and the crowd takes field goals either way", () => {
    expect(names(cues("kickoff"))).toContain("kick");
    expect(names(cues("kickoff"))).not.toContain("cadence"); // (no snap count on a kickoff)
    expect(names(cues("fieldGoal"))).toEqual(expect.arrayContaining(["kick", "cheer"]));
    expect(reaction(PLAYS.missedFieldGoal)).toEqual({ side: "away", big: true });
    expect(names(cues("missedFieldGoal"))).toContain("groan");
  });

  it("blows the whistle on a false start without a crowd reaction", () => {
    const foul = cues("falseStart");
    expect(names(foul)).toContain("flag");
    expect(foul.some((c) => c.reaction)).toBe(false);
  });
});

describe("the crowd's level", () => {
  const play = (quarter: number, home: number, away: number) =>
    makePlay({ quarter, score: { home, away } });
  it("rises late in close games and in the playoffs", () => {
    const early = crowdLevel(play(1, 0, 0), { stage: "regular" });
    const lateClose = crowdLevel(play(4, 17, 14), { stage: "regular" });
    const lateBlowout = crowdLevel(play(4, 35, 3), { stage: "regular" });
    const playoffs = crowdLevel(play(1, 0, 0), { stage: "playoff" });
    expect(lateClose).toBeGreaterThan(early);
    expect(lateBlowout).toBe(early);
    expect(playoffs).toBeGreaterThan(early);
    expect(crowdLevel(play(5, 20, 20), { stage: "playoff" })).toBeLessThanOrEqual(0.8);
  });
});

describe("playing cues as the playhead passes them", () => {
  const list: SoundCue[] = [{ t: 0.5, sound: "snap", gain: 1 }, { t: 0.6, sound: "hit", gain: 1 }];
  it("plays what it passed, once, and nothing on a seek", () => {
    expect(names(dueCues(list, 0.45, 0.55))).toEqual(["snap"]);
    expect(names(dueCues(list, 0.55, 0.65))).toEqual(["hit"]);
    expect(dueCues(list, 0.6, 0.62)).toEqual([]); // already played
    expect(dueCues(list, 0, 2)).toEqual([]); // a jump (scrubbing): skip
    expect(dueCues(list, 0.7, 0.4)).toEqual([]); // backwards
  });
});
