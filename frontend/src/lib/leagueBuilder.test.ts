import { describe, expect, it } from "vitest";
import { makeSpec } from "@/test/fixtures";
import {
  duplicateAbbreviations,
  renameConference,
  renameDivision,
  specProblems,
  structureError,
  totalTeams,
  updateTeam,
} from "./leagueBuilder";

describe("structure", () => {
  it("totals and validates", () => {
    expect(totalTeams({ conferences: 2, divisions: 4, teamsPerDivision: 4 })).toBe(32);
    expect(structureError({ conferences: 2, divisions: 4, teamsPerDivision: 4 })).toBeNull();
    expect(structureError({ conferences: 1, divisions: 1, teamsPerDivision: 3 })).toMatch(/at least 4/);
    expect(structureError({ conferences: 1, divisions: 1, teamsPerDivision: 5 })).toMatch(/even number/);
    expect(structureError({ conferences: 4, divisions: 4, teamsPerDivision: 3 })).toMatch(/at most 40/);
  });
});

describe("spec editing", () => {
  it("updates one team immutably", () => {
    const spec = makeSpec();
    const next = updateTeam(spec, [0, 1, 0], { nickname: "Krakens" });
    expect(next.conferences[0].divisions[1].teams[0].nickname).toBe("Krakens");
    expect(spec.conferences[0].divisions[1].teams[0].nickname).toBe("Nick CCC");
  });

  it("keeps the user's team selected when its abbreviation changes", () => {
    const next = updateTeam(makeSpec(), [0, 0, 0], { abbreviation: "zzz" });
    expect(next.user_team).toBe("ZZZ");
    const other = updateTeam(makeSpec(), [0, 0, 1], { abbreviation: "YYY" });
    expect(other.user_team).toBe("AAA");
  });

  it("renames conferences and divisions", () => {
    const spec = renameDivision(renameConference(makeSpec(), 0, "Mountain"), 0, 1, "Summit");
    expect(spec.conferences[0].name).toBe("Mountain");
    expect(spec.conferences[0].divisions[1].name).toBe("Summit");
  });
});

describe("validation", () => {
  it("accepts a good spec", () => {
    expect(specProblems(makeSpec())).toEqual([]);
  });

  it("finds duplicate abbreviations case-insensitively", () => {
    const spec = updateTeam(makeSpec(), [0, 1, 1], { abbreviation: "bbb" });
    expect(duplicateAbbreviations(spec)).toEqual(new Set(["BBB"]));
    expect(specProblems(spec)).toContain("Abbreviations used twice: BBB.");
  });

  it("reports missing fields and a missing user team", () => {
    let spec = updateTeam(makeSpec(), [0, 0, 1], { city: " " });
    spec = { ...spec, name: "", abbreviation: "X", user_team: "NOPE" };
    expect(specProblems(spec)).toEqual([
      "Give the league a name.",
      "League abbreviation must be 2–8 letters or digits.",
      "Every team needs a city, nickname, and stadium.",
      "Pick your team.",
    ]);
  });
});
