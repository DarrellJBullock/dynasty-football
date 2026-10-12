import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Captions } from "@/components/sound/Captions";
import { choreographGame } from "@/components/field/playback/choreograph";
import type { PlaybackPlay, PlayEvent } from "@/lib/types";
import { makePlay, makePlayback, opponent, pid, team } from "@/test/fixtures";
import { captionAt, commentaryFor, type CommentaryLine } from "./commentary";
import { speechPlan } from "./sound/voices";

const H = team.id;
const A = opponent.id;

const kick = (events: PlayEvent[], overrides: Partial<PlaybackPlay> = {}) =>
  makePlay({ down: null, distance: null, ball_on: null, defense: null, personnel: null, events,
             result: { type: events[0].t }, ...overrides });

const PLAYS: Record<string, PlaybackPlay> = {
  kickoff: kick([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 24, returner: pid(H, "WR") }],
                { side: "away" }),
  run: makePlay({ result: { type: "run", yards: 6 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" }, { t: "rush", player: pid(H, "RB"), yards: 6 },
             { t: "tackle", by: [pid(A, "MLB")] }] }),
  complete: makePlay({ down: 3, distance: 5, result: { type: "pass", yards: 14, result: "complete", first_down: true },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "short" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR"), result: "complete", air: 8, yards: 14 },
             { t: "tackle", by: [pid(A, "CB")] }] }),
  defended: makePlay({ result: { type: "pass", yards: 0, result: "incomplete" },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "deep" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR", 1), result: "incomplete", air: 30, yards: 0 },
             { t: "pass_defended", by: pid(A, "CB", 1) }] }),
  interception: makePlay({ result: { type: "pass", yards: 0, result: "interception", turnover: true },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "TE"), result: "interception", air: 15, yards: 0 },
             { t: "interception", by: pid(A, "FS"), return: 12 }] }),
  sack: makePlay({ result: { type: "sack", yards: -7 },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" }, { t: "sack", qb: pid(H, "QB"), by: pid(A, "DE"), yards: -7 }] }),
  holding: makePlay({ result: { type: "penalty", nullified: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" }, { t: "rush", player: pid(H, "RB"), yards: 9 },
             { t: "tackle", by: [pid(A, "MLB")] },
             { t: "penalty", team: team.abbreviation, kind: "holding", yards: 10, player: pid(H, "OT"), automatic_first: false }] }),
  falseStart: makePlay({ result: { type: "penalty" },
    events: [{ t: "penalty", team: team.abbreviation, kind: "false_start", yards: 5, player: pid(H, "OT"), automatic_first: false }] }),
  hurt: makePlay({ result: { type: "run", yards: 3 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" }, { t: "rush", player: pid(H, "RB"), yards: 3 },
             { t: "tackle", by: [pid(A, "MLB")] },
             { t: "injury", player: pid(H, "RB"), team: team.abbreviation, injury: "Ankle sprain", weeks: 1 }] }),
  touchdown: makePlay({ ball_on: 88, result: { type: "run", yards: 12, touchdown: true }, score: { home: 6, away: 0 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "outside" }, { t: "rush", player: pid(H, "RB"), yards: 12 }] }),
  extraPoint: kick([{ t: "extra_point", kicker: pid(H, "K"), good: true }], { score: { home: 7, away: 0 } }),
  punt: kick([{ t: "punt", punter: pid(H, "P"), yards: 45, touchback: false, fair_catch: true, return: 0, returner: pid(A, "WR") }],
             { down: 4, distance: 6, ball_on: 40 }),
  fieldGoal: kick([{ t: "field_goal", kicker: pid(H, "K"), distance: 42, good: false }], { down: 4, distance: 3, ball_on: 75 }),
};
const names = Object.keys(PLAYS);
const playback = makePlayback(Object.values(PLAYS));
const timelines = choreographGame(playback).map((c) => c.timeline);
const lines = (name: string) => commentaryFor(playback, names.indexOf(name), timelines[names.indexOf(name)]);
const said = (name: string) => lines(name).map((l) => l.text).join(" ");
const lastName = (id: number) => playback.players.find((p) => p.id === id)!.name.split(" ").slice(-1)[0];

describe("the play-by-play", () => {
  it("calls every kind of play, in time with it", () => {
    for (const [i, name] of names.entries()) {
      const call = commentaryFor(playback, i, timelines[i]);
      expect(call.length, name).toBeGreaterThan(0);
      expect(call.every((l) => l.t >= 0 && l.t <= timelines[i].duration), name).toBe(true);
      expect(call.map((l) => l.t)).toEqual([...call.map((l) => l.t)].sort((a, b) => a - b));
    }
  });

  it("names the players by their last names", () => {
    expect(said("run")).toContain(lastName(pid(H, "RB")));
    expect(said("run")).toContain(`brought down by ${lastName(pid(A, "MLB"))}`);
    expect(said("complete")).toContain(`${lastName(pid(H, "WR"))}`);
    expect(said("complete")).toContain("and that's a first down");
    expect(said("defended")).toContain(`broken up by ${lastName(pid(A, "CB", 1))}`);
    expect(said("interception")).toContain(`Intercepted! ${lastName(pid(A, "FS"))} picks it off and brings it back 12!`);
    expect(said("sack")).toContain(lastName(pid(A, "DE")));
    expect(said("kickoff")).toContain(`brings it back 24 yards`);
  });

  it("calls the kicks, the score and the fouls", () => {
    expect(said("touchdown")).toMatch(/Touchdown/);
    expect(said("extraPoint")).toMatch(/good/);
    expect(said("fieldGoal")).toMatch(/from 42…/);
    expect(said("fieldGoal")).toMatch(/No good!|It's wide!/);
    expect(said("punt")).toContain("calls for the fair catch");
    expect(said("falseStart")).toContain(`Flag before the snap: false start, ${team.abbreviation}. 5 yards.`);
    expect(said("holding")).toContain("there's a flag on the play");
  });

  it("calls the same play the same way every time", () => {
    expect(lines("complete")).toEqual(lines("complete"));
  });
});

describe("the analyst", () => {
  const color = (name: string) => lines(name).filter((l) => l.voice === "color").map((l) => l.text);
  it("explains a foul that wiped out a play", () => {
    expect(color("holding")).toEqual([`That's offensive holding on ${team.abbreviation}. 10 yards, and the play comes back.`]);
  });
  it("notices an injury", () => {
    expect(color("hurt")[0]).toMatch(/is slow to get up… looks like ankle sprain/);
  });
  it("speaks after the play, not over it", () => {
    for (const [i, name] of names.entries()) {
      const whistle = timelines[i].moments.find((m) => m.kind === "whistle")?.t ?? timelines[i].duration;
      for (const line of lines(name).filter((l) => l.voice === "color")) {
        expect(line.t).toBeGreaterThanOrEqual(Math.min(whistle, timelines[i].duration));
      }
    }
  });
  it("signs off at the end of the game", () => {
    expect(color("fieldGoal")[0]).toMatch(/^And that's the ball game\./); // (the last play here)
  });
});

describe("spoken", () => {
  it("most of the call fits when it's said aloud, and every play gets some", () => {
    let total = 0;
    let said = 0;
    for (const [i, name] of names.entries()) {
      const call = commentaryFor(playback, i, timelines[i]);
      const spoken = speechPlan(call, timelines[i].duration);
      expect(spoken.length, name).toBeGreaterThan(0);
      total += call.length;
      said += spoken.length;
    }
    expect(said / total).toBeGreaterThan(0.6);
  });
});

describe("words", () => {
  it("never assumes a player's gender (leagues can be men's or women's)", () => {
    const all: CommentaryLine[] = names.flatMap((name) => lines(name));
    // Every phrasing, too: call each play as if it were each of several games.
    for (let g = 1; g <= 12; g++) {
      const other = { ...playback, game: { ...playback.game, id: g } };
      for (const [i] of names.entries()) all.push(...commentaryFor(other, i, timelines[i]));
    }
    for (const line of all) expect(line.text).not.toMatch(/\b(he|him|his|she|her|hers)\b/i);
  });
});

describe("captions", () => {
  const call: CommentaryLine[] = [{ t: 1, voice: "play", text: "Handoff to Banks…" },
                                  { t: 3, voice: "play", text: "Gains 6." }, { t: 4, voice: "color", text: "Nice run." }];
  it("show the line being said, for a few seconds", () => {
    expect(captionAt(call, 0.5)).toBeNull();
    expect(captionAt(call, 2)?.text).toBe("Handoff to Banks…");
    expect(captionAt(call, 3.5)?.text).toBe("Gains 6.");
    expect(captionAt(call, 9)).toBeNull();
  });
  it("label the analyst for screen readers", () => {
    render(<Captions lines={call} time={4.2} />);
    expect(screen.getByRole("log", { name: "Commentary" })).toHaveTextContent("Analyst: Nice run.");
  });
});
