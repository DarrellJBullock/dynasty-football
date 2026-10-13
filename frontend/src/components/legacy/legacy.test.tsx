import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { HallOfFame, HallOfFamer, RecordCategory, RecordRow, TeamRecords } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { HallOfFameView } from "./HallOfFameView";
import { RecordsView } from "./RecordsView";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { retireNumber: vi.fn() } };
});
const mocked = vi.mocked(api);

function famer(id: number, overrides: Partial<HallOfFamer> = {}): HallOfFamer {
  return { player_id: id, name: `Legend ${id}`, position: "QB", year: 2040, team, score: 71.5,
    case: "2× MVP · 1 title · 41,250 pass yds · 12 seasons", inducted: true, retired_year: 2036, ...overrides };
}

const hall: HallOfFame = {
  members: [famer(1), famer(2, { year: 2041, position: "OG", case: "10,500 snaps · 11 seasons" })]
    .sort((a, b) => b.year - a.year),
  ballot_year: 2041, near_misses: [famer(3, { inducted: false, score: 58.2, year: 2041 })],
  retired_numbers: [{ team, number: 12, player_id: 1, name: "Legend 1", year: 2040 }],
  eligible_after: 3, bar: 60,
};

beforeEach(() => vi.clearAllMocks());

describe("HallOfFameView", () => {
  it("lists each class, the near misses, and retired numbers", () => {
    render(<HallOfFameView hall={hall} league="Harbor League" />);
    const latest = screen.getByRole("list", { name: "Class of 2041" });
    expect(within(latest).getByRole("listitem", { name: "Legend 2" })).toHaveTextContent("10,500 snaps · 11 seasons");
    expect(screen.getByRole("list", { name: "Class of 2040" })).toHaveTextContent("2× MVP");
    expect(screen.getByRole("list", { name: "Near misses" })).toHaveTextContent("58.2");
    expect(screen.getByRole("list", { name: "Retired numbers" })).toHaveTextContent("12Legend 1");
  });

  it("explains when there's no one yet", () => {
    render(<HallOfFameView hall={{ ...hall, members: [], near_misses: [], retired_numbers: [], ballot_year: null }}
      league="Harbor League" />);
    expect(screen.getByText(/No one yet/)).toHaveTextContent("retired 3 seasons");
  });
});

const row = (id: number, value: number, year: number | null): RecordRow => ({ player_id: id,
  name: `Player ${id}`, position: "QB", team: "HFD", year, value, games: year ? 1 : 30, retired: false });
const passing: RecordCategory = { key: "passing_yards", label: "Passing yards",
  single_game: [row(1, 512, 2031)], single_season: [row(1, 4900, 2031)], career: [row(1, 31000, null)] };
const book: TeamRecords = { team, records: [passing], hall_of_famers: [famer(1)],
  retired_numbers: [], retire_candidates: [
    { player_id: 1, name: "Legend 1", position: "QB", number: 12, hall_of_fame: true },
    { player_id: 4, name: "Old Guard", position: "OG", number: 66, hall_of_fame: false },
  ] };

describe("RecordsView", () => {
  it("shows the team's records by game, season and career, and switches teams", async () => {
    render(<RecordsView initial={book} teams={[team, opponent]} />);
    const group = screen.getByRole("group", { name: "Passing yards" });
    expect(group).toHaveTextContent("4,900");
    await userEvent.click(screen.getByRole("tab", { name: "Single game" }));
    expect(group).toHaveTextContent("512");
    await userEvent.click(screen.getByRole("tab", { name: "Career" }));
    expect(group).toHaveTextContent("31,000");
    await userEvent.selectOptions(screen.getByLabelText("Team"), String(opponent.id));
    expect(router.push).toHaveBeenCalledWith(`/records?team=${opponent.id}`);
  });

  it("retires a former player's number, and shows why one can't be", async () => {
    mocked.retireNumber
      .mockResolvedValueOnce({ ...book, retired_numbers: [{ team, number: 12, player_id: 1, name: "Legend 1", year: 2041 }],
        retire_candidates: [book.retire_candidates[1]] })
      .mockRejectedValueOnce(new ApiError(409, "The Ironclads already retired number 66."));
    render(<RecordsView initial={book} teams={[team]} />);
    const choices = screen.getByRole("list", { name: "Numbers you could retire" });
    expect(choices).toHaveTextContent("Hall of Fame");
    await userEvent.click(within(choices).getByRole("button", { name: "Retire #12" }));
    expect(mocked.retireNumber).toHaveBeenCalledWith(team.id, 1);
    expect(await screen.findByRole("status")).toHaveTextContent("Number 12 is retired");
    expect(screen.getByRole("list", { name: "Retired numbers" })).toHaveTextContent("12Legend 1");
    await userEvent.click(screen.getByRole("button", { name: "Retire #66" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already retired number 66");
  });

  it("offers nothing to retire to someone else's team", () => {
    render(<RecordsView initial={{ ...book, retire_candidates: [] }} teams={[team]} />);
    expect(screen.queryByRole("region", { name: "Retire a number" })).toBeNull();
  });
});
