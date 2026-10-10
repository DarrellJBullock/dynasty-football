import { describe, expect, it } from "vitest";
import { makePlayer } from "@/test/fixtures";
import { DEFAULT_SORT, filterRoster, groupCounts, nextSort, sortRoster } from "./roster";

const qb = makePlayer({ first_name: "Alpha", last_name: "Zed", position: "QB", overall: 82, age: 30, jersey_number: 12 });
const wr = makePlayer({ first_name: "Bravo", last_name: "Young", position: "WR", position_group: "WR", overall: 88, age: 24, jersey_number: 81 });
const cb = makePlayer({ first_name: "Charlie", last_name: "Adams", position: "CB", position_group: "DB", overall: 70, age: 27, jersey_number: 24, contract: null });
const roster = [qb, wr, cb];

describe("filterRoster", () => {
  it("returns everyone for ALL with no search", () => {
    expect(filterRoster(roster, "ALL", "")).toHaveLength(3);
  });

  it("filters by position group", () => {
    expect(filterRoster(roster, "DB", "")).toEqual([cb]);
  });

  it("searches names case-insensitively", () => {
    expect(filterRoster(roster, "ALL", "  YOUNG ")).toEqual([wr]);
  });

  it("matches exact position or jersey number", () => {
    expect(filterRoster(roster, "ALL", "qb")).toEqual([qb]);
    expect(filterRoster(roster, "ALL", "24")).toEqual([cb]);
  });

  it("combines group and search", () => {
    expect(filterRoster(roster, "QB", "young")).toEqual([]);
  });
});

describe("sortRoster", () => {
  it("sorts by overall descending by default", () => {
    expect(sortRoster(roster, DEFAULT_SORT).map((p) => p.id)).toEqual([wr.id, qb.id, cb.id]);
  });

  it("sorts by last name ascending", () => {
    const sorted = sortRoster(roster, { key: "last_name", direction: "asc" });
    expect(sorted.map((p) => p.last_name)).toEqual(["Adams", "Young", "Zed"]);
  });

  it("sorts positions in depth-chart order", () => {
    const sorted = sortRoster(roster, { key: "position", direction: "asc" });
    expect(sorted.map((p) => p.position)).toEqual(["QB", "WR", "CB"]);
  });

  it("treats missing contracts as zero salary", () => {
    const sorted = sortRoster(roster, { key: "salary", direction: "asc" });
    expect(sorted[0]).toBe(cb);
  });

  it("does not mutate the input", () => {
    const copy = [...roster];
    sortRoster(roster, { key: "age", direction: "asc" });
    expect(roster).toEqual(copy);
  });
});

describe("nextSort", () => {
  it("toggles direction on the active column", () => {
    expect(nextSort({ key: "overall", direction: "desc" }, "overall")).toEqual({ key: "overall", direction: "asc" });
  });

  it("uses each column's natural direction when switching", () => {
    expect(nextSort(DEFAULT_SORT, "last_name").direction).toBe("asc");
    expect(nextSort(DEFAULT_SORT, "salary").direction).toBe("desc");
  });
});

describe("groupCounts", () => {
  it("counts players per group plus ALL", () => {
    expect(groupCounts(roster)).toMatchObject({ ALL: 3, QB: 1, WR: 1, DB: 1 });
  });
});
