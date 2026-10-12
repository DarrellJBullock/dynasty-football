import { describe, expect, it } from "vitest";
import {
  expectedReturn,
  formatAttribute,
  formatHeight,
  formatMoney,
  formatRecord,
  injuryDetail,
  injuryDuration,
  injuryHistory,
  injuryLabel,
  releaseCost,
  ratingTier,
  yearsRemaining,
} from "./format";

describe("formatMoney", () => {
  it.each([
    [255_000_000, "$255M"],
    [15_320_000, "$15.3M"],
    [1_000_000, "$1.0M"],
    [750_000, "$750K"],
    [940, "$940"],
    [0, "$0"],
    [-2_500_000, "-$2.5M"],
  ])("%d -> %s", (input, expected) => {
    expect(formatMoney(input)).toBe(expected);
  });
});

describe("formatters", () => {
  it("formats height in feet and inches", () => {
    expect(formatHeight(74)).toBe(`6'2"`);
    expect(formatHeight(72)).toBe(`6'0"`);
  });

  it("omits ties from records unless present", () => {
    expect(formatRecord({ wins: 10, losses: 7, ties: 0 })).toBe("10-7");
    expect(formatRecord({ wins: 9, losses: 7, ties: 1 })).toBe("9-7-1");
  });

  it("title-cases attribute names", () => {
    expect(formatAttribute("ball_carrier_vision")).toBe("Ball Carrier Vision");
    expect(formatAttribute("speed")).toBe("Speed");
  });

  it("labels injury statuses", () => {
    expect(injuryLabel("injured_reserve")).toBe("IR");
    expect(injuryLabel("questionable")).toBe("Questionable");
  });

  it("counts remaining contract years including the current season", () => {
    expect(yearsRemaining(2027, 2026)).toBe(2);
    expect(yearsRemaining(2026, 2026)).toBe(1);
    expect(yearsRemaining(2024, 2026)).toBe(0);
  });
});

describe("ratingTier", () => {
  it.each([
    [99, "elite"],
    [90, "elite"],
    [89, "great"],
    [80, "great"],
    [75, "good"],
    [60, "average"],
    [59, "poor"],
  ])("%d is %s", (value, tier) => {
    expect(ratingTier(value)).toBe(tier);
  });
});

describe("injuries", () => {
  it("describes how long a player is out", () => {
    expect(injuryDuration(0)).toBe("Questionable, playing hurt");
    expect(injuryDuration(1)).toBe("Out 1 game");
    expect(injuryDuration(3)).toBe("Out 3 games");
    expect(injuryDuration(99)).toBe("Out for the season");
  });

  it("describes simulated and hand-set injuries", () => {
    expect(injuryDetail({ injury_status: "out", injury: "Knee sprain", injury_weeks: 2 }))
      .toBe("Knee sprain · Out 2 games");
    expect(injuryDetail({ injury_status: "injured_reserve", injury: null })).toBe("IR");
    expect(injuryDetail({ injury_status: "healthy" })).toBe("Healthy");
  });

  it("says when an injured player is expected back", () => {
    const season = { phase: "regular_season", current_week: 7, weeks: 17 };
    expect(expectedReturn(2, season)).toBe("back week 9");
    expect(expectedReturn(11, season)).toBe("back after the regular season");
    expect(expectedReturn(0, season)).toBeNull(); // questionable: he plays
    expect(expectedReturn(99, season)).toBeNull(); // out for the season
    expect(expectedReturn(2, { ...season, phase: "playoffs" })).toBeNull();
    expect(expectedReturn(2)).toBeNull();
    expect(injuryDetail({ injury_status: "out", injury: "Knee sprain", injury_weeks: 2 }, season))
      .toBe("Knee sprain · Out 2 games · back week 9");
    expect(injuryDetail({ injury_status: "injured_reserve", injury: "Torn ACL", injury_weeks: 99 },
                        season)).toBe("Torn ACL · Out for the season");
  });

  it("counts career injuries", () => {
    expect(injuryHistory(0)).toBeNull();
    expect(injuryHistory(undefined)).toBeNull();
    expect(injuryHistory(1)).toBe("1 career injury");
    expect(injuryHistory(3)).toBe("3 career injuries");
  });
});

describe("releaseCost", () => {
  const contract = { signing_bonus: 12_000_000, years: 4, end_year: 2029 };
  it("is the bonus left from the cap year to the end of the deal", () => {
    expect(releaseCost(contract, 2026)).toBe(12_000_000);
    expect(releaseCost(contract, 2028)).toBe(6_000_000);
    expect(releaseCost(contract, 2030)).toBe(0);
    expect(releaseCost(null, 2026)).toBe(0);
  });
});
