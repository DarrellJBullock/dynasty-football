import { describe, expect, it } from "vitest";
import { makePlay } from "@/test/fixtures";
import { highlightIndexes, highlightReason } from "./highlights";

const run = (yards: number, extra = {}) => makePlay({
  result: { type: "run", yards }, events: [{ t: "rush", player: 101, yards }], ...extra });

describe("highlights", () => {
  it("picks scores, turnovers, big plays and missed kicks", () => {
    expect(highlightReason(run(4), undefined)).toBeNull();
    expect(highlightReason(run(24), undefined)).toBe("big play");
    expect(highlightReason(run(3, { score: { home: 7, away: 0 } }), run(0))).toBe("score");
    expect(highlightReason(makePlay({
      result: { type: "pass", yards: 0, turnover: true },
      events: [{ t: "pass", qb: 100, target: 102, result: "interception", air: 12, yards: 0 },
               { t: "interception", by: 218, return: 4 }] }), undefined)).toBe("turnover");
    expect(highlightReason(run(3, { events: [{ t: "rush", player: 101, yards: 3 },
      { t: "fumble", player: 101, forced_by: 218, lost: true }] }), undefined)).toBe("turnover");
    expect(highlightReason(makePlay({ result: { type: "field_goal", good: false },
      events: [{ t: "field_goal", kicker: 124, distance: 51, good: false }] }), undefined)).toBe("missed kick");
    // A big gain called back for a penalty isn't one.
    expect(highlightReason(run(30, { result: { type: "penalty", nullified: true } }), undefined)).toBeNull();
  });

  it("lists a game's highlights in order", () => {
    const plays = [run(3), run(25), run(2), run(4, { score: { home: 6, away: 0 } }), run(1, { score: { home: 6, away: 0 } })];
    expect(highlightIndexes(plays)).toEqual([1, 3]);
  });
});
