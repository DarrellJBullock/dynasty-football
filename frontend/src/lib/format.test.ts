import { describe, expect, it } from "vitest";
import {
  formatAttribute,
  formatHeight,
  formatMoney,
  formatRecord,
  injuryLabel,
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
