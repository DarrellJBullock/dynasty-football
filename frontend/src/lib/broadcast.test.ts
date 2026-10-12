import { describe, expect, it } from "vitest";
import { choreograph, SNAP } from "@/components/field/playback/choreograph";
import type { PlaybackPlay } from "@/lib/types";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { bannerAt, bannersFor, clockSeconds, downText, formatClock, gameClockAt, playClockAt,
         scoreAt } from "./broadcast";

const H = 1;
const A = 2;
const playback = makePlayback([]);
const timelineOf = (play: PlaybackPlay) => choreograph(play, playback).timeline;
const whistleOf = (play: PlaybackPlay) =>
  timelineOf(play).moments.find((m) => m.kind === "whistle")!.t;

const run = (overrides: Partial<PlaybackPlay> = {}) => makePlay({
  clock: "4:31", seconds: 6, result: { type: "run", yards: 12, first_down: true },
  events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
           { t: "rush", player: pid(H, "RB"), yards: 12 }, { t: "tackle", by: [pid(A, "MLB")] }],
  ...overrides,
});

describe("the game clock", () => {
  it("parses and formats clock labels", () => {
    expect(clockSeconds("4:31")).toBe(271);
    expect(formatClock(271)).toBe("4:31");
    expect(formatClock(9)).toBe("0:09");
    expect(formatClock(-3)).toBe("0:00");
  });

  it("runs from the snap to the whistle through the play's seconds", () => {
    const play = run();
    const timeline = timelineOf(play);
    expect(gameClockAt(play, timeline, 0)).toBe(271);
    expect(gameClockAt(play, timeline, SNAP)).toBe(271);
    const mid = gameClockAt(play, timeline, (SNAP + whistleOf(play)) / 2);
    expect(mid).toBeLessThan(271);
    expect(mid).toBeGreaterThan(265);
    expect(gameClockAt(play, timeline, whistleOf(play))).toBe(265);
    expect(gameClockAt(play, timeline, timeline.duration)).toBe(265);
  });

  it("stays put for old logs without play seconds, and never goes below zero", () => {
    const old = run({ seconds: undefined });
    expect(gameClockAt(old, timelineOf(old), 99)).toBe(271);
    const late = run({ clock: "0:03", seconds: 6 });
    expect(gameClockAt(late, timelineOf(late), 99)).toBe(0);
  });

  it("shows the play clock only before the snap, and only for scrimmage downs", () => {
    const play = run();
    const left = playClockAt(play, 0)!;
    expect(left).toBeGreaterThanOrEqual(4);
    expect(playClockAt(play, 0.99)).toBe(left);
    expect(playClockAt(play, SNAP)).toBeNull();
    expect(playClockAt(run({ down: null }), 0)).toBeNull();
  });
});

describe("the score and the down", () => {
  it("adds the points when they're scored, not before", () => {
    const before = run({ score: { home: 7, away: 3 } });
    const td = run({ ball_on: 88, score: { home: 13, away: 3 },
      result: { type: "run", yards: 12, touchdown: true },
      events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
               { t: "rush", player: pid(H, "RB"), yards: 12 }] });
    const timeline = timelineOf(td);
    const scored = timeline.moments.find((m) => m.kind === "touchdown")!.t;
    expect(scoreAt(td, before, timeline, scored - 0.1)).toEqual({ home: 7, away: 3 });
    expect(scoreAt(td, before, timeline, scored)).toEqual({ home: 13, away: 3 });
    expect(scoreAt(before, before, timelineOf(before), 0)).toEqual({ home: 7, away: 3 }); // no change
  });

  it("names the down", () => {
    expect(downText(run({ down: 3, distance: 4 }))).toBe("3rd & 4");
    expect(downText(run({ down: 1, distance: 10, ball_on: 95 }))).toBe("1st & Goal");
    expect(downText(makePlay({ down: null, events: [{ t: "kickoff", kicker: 1, touchback: true, return: 0 }] })))
      .toBe("Kickoff");
    expect(downText(makePlay({ down: null, events: [{ t: "extra_point", kicker: 1, good: true }] }))).toBe("PAT");
  });
});

describe("banners", () => {
  it("first downs, touchdowns, turnovers, sacks, flags and kicks", () => {
    const first = run();
    expect(bannersFor(first, timelineOf(first)).map((b) => b.text)).toEqual(["First down"]);

    const sack = run({ result: { type: "sack", yards: -7 },
      events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
               { t: "sack", qb: pid(H, "QB"), by: pid(A, "DE"), yards: -7 },
               { t: "fumble", player: pid(H, "QB"), forced_by: pid(A, "DE"), lost: true }] });
    expect(bannersFor(sack, timelineOf(sack)).map((b) => b.text)).toEqual(["Sack", "Fumble"]);

    const held = run({ result: { type: "penalty", nullified: true },
      events: [...run().events, { t: "penalty", team: "offense", kind: "holding", yards: 10,
                                  player: pid(H, "OT"), automatic_first: false }] });
    const banners = bannersFor(held, timelineOf(held));
    expect(banners.map((b) => [b.text, b.tone])).toEqual([["Flag · Offensive holding", "flag"]]);

    // A personal foul: the play stands, then the flag.
    const roughed = run({ result: { type: "run", yards: 4, first_down: true },
      events: [...run().events, { t: "penalty", team: "AWY", kind: "unnecessary_roughness",
                                  yards: 15, player: pid(A, "MLB"),
                                  automatic_first: true }] });
    expect(bannersFor(roughed, timelineOf(roughed)).map((b) => b.text))
      .toContain("Flag · Unnecessary roughness");

    const miss = makePlay({ down: 4, distance: 6, ball_on: 60, personnel: null, defense: null,
      result: { type: "field_goal", good: false },
      events: [{ t: "field_goal", kicker: pid(H, "K"), distance: 57, good: false }] });
    expect(bannersFor(miss, timelineOf(miss))).toMatchObject([{ text: "No good", tone: "red" }]);
  });

  it("shows one banner at a time, for a couple of seconds", () => {
    const banners = [{ t: 2, text: "Sack", tone: "red" as const }, { t: 2.5, text: "Fumble", tone: "red" as const }];
    expect(bannerAt(banners, 1.9)).toBeNull();
    expect(bannerAt(banners, 2.1)?.text).toBe("Sack");
    expect(bannerAt(banners, 3)?.text).toBe("Fumble");
    expect(bannerAt(banners, 5)).toBeNull();
  });
});
