import { describe, expect, it } from "vitest";
import type { PlaybackPlay } from "@/lib/types";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { breakAfter, driveEndingAt, statLowerThird, statsThrough } from "./gameStats";

const H = 1;
const A = 2;
const qb = pid(H, "QB");
const rb = pid(H, "RB");
const wr = pid(H, "WR");
const kick = (side: "home" | "away", extra: Partial<PlaybackPlay> = {}) => makePlay({
  side, offense: side === "home" ? "HFD" : "ABQ", down: null, distance: null, ball_on: null, personnel: null,
  defense: null, result: { type: "kickoff" },
  events: [{ t: "kickoff", kicker: pid(side === "home" ? H : A, "K"), touchback: true, return: 0 }], ...extra });

const plays = makePlayback([
  kick("away", { quarter: 2, clock: "6:00" }), // 0
  makePlay({ quarter: 2, ball_on: 25, elapsed: 35, result: { type: "run", yards: 8 }, // 1
    events: [{ t: "rush", player: rb, yards: 8 }, { t: "tackle", by: [pid(A, "MLB")] }] }),
  makePlay({ quarter: 2, down: 2, distance: 2, ball_on: 33, elapsed: 30, // 2
    result: { type: "pass", yards: 12, result: "complete", first_down: true },
    events: [{ t: "pass", qb, target: wr, result: "complete", air: 9, yards: 12 }, { t: "tackle", by: [pid(A, "CB")] }] }),
  makePlay({ quarter: 2, ball_on: 45, elapsed: 32, result: { type: "penalty", nullified: true }, // 3: wiped out
    events: [{ t: "rush", player: rb, yards: 20 }, { t: "penalty", team: "offense", kind: "holding", yards: 10,
                                                      player: pid(H, "OT"), automatic_first: false }] }),
  makePlay({ quarter: 2, ball_on: 35, elapsed: 8, score: { home: 6, away: 0 }, // 4: touchdown
    result: { type: "pass", yards: 65, result: "complete", touchdown: true },
    events: [{ t: "pass", qb, target: wr, result: "complete", air: 40, yards: 65 }] }),
  makePlay({ quarter: 2, down: null, distance: null, ball_on: null, personnel: null, defense: null, // 5
    score: { home: 7, away: 0 }, result: { type: "conversion" }, events: [{ t: "extra_point", kicker: pid(H, "K"), good: true }] }),
  kick("home", { quarter: 2, score: { home: 7, away: 0 } }), // 6
  makePlay({ quarter: 2, side: "away", offense: "ABQ", ball_on: 25, score: { home: 7, away: 0 }, // 7: picked off
    result: { type: "pass", yards: 0, result: "interception", turnover: true },
    events: [{ t: "pass", qb: pid(A, "QB"), target: pid(A, "WR"), result: "interception", air: 15, yards: 0 },
             { t: "interception", by: pid(H, "CB", 1), return: 5 }] }),
  makePlay({ quarter: 2, ball_on: 55, score: { home: 7, away: 0 }, result: { type: "kneel", yards: -1 }, // 8
    events: [{ t: "kneel", qb, yards: -1 }] }),
  kick("away", { quarter: 3, score: { home: 7, away: 0 } }), // 9
]).plays;
const roster = new Map(makePlayback([]).players.map((p) => [p.id, p]));

describe("running stats", () => {
  it("folds player and team lines from the events, like the box score", () => {
    const { players, teams } = statsThrough(plays, 4);
    expect(players.get(qb)).toMatchObject({ pass_att: 2, pass_cmp: 2, pass_yds: 77, pass_td: 1 });
    expect(players.get(wr)).toMatchObject({ receptions: 2, rec_yds: 77, rec_td: 1 });
    expect(players.get(rb)).toMatchObject({ rush_att: 1, rush_yds: 8 }); // the holding call wiped a carry
    expect(players.get(pid(A, "MLB"))?.tackles).toBe(1);
    expect(teams.home).toMatchObject({ total_yds: 85, rush_yds: 8, pass_yds: 77, first_downs: 2, plays: 3 });
    expect(teams.home.time_of_possession).toBe(35 + 30 + 32 + 8);
    expect(statsThrough(plays, 7).teams.away.turnovers).toBe(1);
  });

  it("stops at the play asked for", () => {
    expect(statsThrough(plays, 1).players.get(qb)).toBeUndefined();
  });
});

describe("stat lower thirds", () => {
  it("puts up the passer on a touchdown pass, the defender on a pick, nothing on a routine play", () => {
    expect(statLowerThird(plays, 4, roster)).toMatchObject({ id: qb, line: "2/2, 77 yds, 1 TD" });
    expect(statLowerThird(plays, 4, roster)?.player?.position).toBe("QB");
    expect(statLowerThird(plays, 7, roster)).toMatchObject({ id: pid(H, "CB", 1), line: "1 INT" });
    expect(statLowerThird(plays, 1, roster)).toBeNull();
    expect(statLowerThird(plays, 3, roster)).toBeNull(); // called back
  });
});

describe("drives", () => {
  it("sums up a drive when it ends", () => {
    expect(driveEndingAt(plays, 2)).toBeNull(); // still going
    expect(driveEndingAt(plays, 4)).toEqual({ side: "home", plays: 4, yards: 75, seconds: 105, result: "Touchdown" });
    expect(driveEndingAt(plays, 7)).toMatchObject({ side: "away", plays: 1, result: "Interception" });
    expect(driveEndingAt(plays, 8)).toMatchObject({ side: "home", result: "End of half" });
    expect(driveEndingAt(plays, 0)).toBeNull(); // kicks aren't drives
  });

  it("knows halftime and the end of the game", () => {
    expect(breakAfter(plays, 8)).toBe("halftime");
    expect(breakAfter(plays, 9)).toBe("final");
    expect(breakAfter(plays, 4)).toBeNull();
  });
});
