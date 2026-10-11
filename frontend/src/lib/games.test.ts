import { describe, expect, it } from "vitest";
import { opponent, team } from "@/test/fixtures";
import type { Game } from "@/lib/types";
import { describeResult, formatPossession, resultFor } from "./games";

function game(overrides: Partial<Game>): Game {
  return { id: 1, week: 3, home: team, away: opponent, home_score: null, away_score: null,
    status: "scheduled", overtime: false, stage: "regular", round_name: null, neutral_site: false,
    ...overrides };
}

describe("resultFor", () => {
  it("reads a game from either team's side", () => {
    const g = game({ status: "final", home_score: 26, away_score: 17 });
    expect(resultFor(g, team.id)).toMatchObject({ outcome: "W", home: true, pointsFor: 26, pointsAgainst: 17 });
    expect(resultFor(g, opponent.id)).toMatchObject({ outcome: "L", home: false, opponent: team });
  });

  it("handles ties and unplayed games", () => {
    expect(resultFor(game({ status: "final", home_score: 20, away_score: 20 }), team.id).outcome).toBe("T");
    expect(resultFor(game({}), team.id).outcome).toBeNull();
  });
});

describe("describeResult", () => {
  it("formats results and upcoming games", () => {
    expect(describeResult(game({ status: "final", home_score: 26, away_score: 17 }), team.id))
      .toBe("W 26-17 vs Roadrunners");
    expect(describeResult(game({ status: "final", home_score: 27, away_score: 24, overtime: true }), opponent.id))
      .toBe("L 24-27 @ Ironclads (OT)");
    expect(describeResult(game({}), team.id)).toBe("Week 3 vs Roadrunners");
  });
});

describe("formatPossession", () => {
  it("formats seconds as m:ss", () => {
    expect(formatPossession(1784)).toBe("29:44");
    expect(formatPossession(65)).toBe("1:05");
  });
});
