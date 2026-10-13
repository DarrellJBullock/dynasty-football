import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { DraftOut, ProspectRow } from "@/lib/types";
import { makePlayer, opponent, team } from "@/test/fixtures";
import { DraftView } from "./DraftView";

const router = { refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { scout: vi.fn(), draftPick: vi.fn(), cutDown: vi.fn(), playDraft: vi.fn() } };
});
const mocked = vi.mocked(api);

function prospect(id: number, overrides: Partial<ProspectRow> = {}): ProspectRow {
  return { id, full_name: `Prospect ${id}`, position: "WR", age: 21, college: "Ridgeview State",
    height_in: 73, weight_lb: 195, projected: 68, low: 64, high: 72, grade: "B+", scouted: false,
    overall: null, potential: null, ...overrides };
}

const season = { id: 6, league_id: 1, year: 2027, phase: "regular_season", current_week: 5, weeks: 17,
  regular_season_complete: false, next_round: null, champion: null };

const upcoming: DraftOut = {
  season, year: 2028, status: "upcoming", picks: [], on_the_clock: null, my_team_id: team.id,
  my_next_pick: null, scouting_left: 24, roster_count: 53, roster_max: 53, clock_ends_at: null,
  prospects: [prospect(1), prospect(2, { scouted: true, projected: 71, low: 71, high: 71,
    overall: 71, potential: 84, grade: "A" })],
};

const live: DraftOut = {
  ...upcoming, year: 2027, status: "live", season: { ...season, phase: "draft" },
  on_the_clock: 3, my_next_pick: 3,
  picks: [
    { round: 1, number: 1, pick_in_round: 1, team: opponent, player: makePlayer({ id: 90, full_name: "First Overall" }) },
    { round: 1, number: 2, pick_in_round: 2, team: opponent, player: makePlayer({ id: 91, full_name: "Second Pick" }) },
    { round: 1, number: 3, pick_in_round: 3, team, player: null },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe("DraftView", () => {
  it("shows the upcoming class through the scouting fog", async () => {
    mocked.scout.mockResolvedValue(prospect(1, { scouted: true }));
    render(<DraftView draft={upcoming} team={team} leagueId={4} />);
    expect(screen.getByRole("heading", { name: "2028 Draft" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("24 scouting report(s) left");
    const rows = within(screen.getByRole("region", { name: "Prospects" })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("64–72");
    expect(rows[1]).toHaveTextContent("B+");
    expect(rows[2]).toHaveTextContent("84 (A)");
    expect(rows[2]).toHaveTextContent("Scouted");
    expect(screen.queryByRole("button", { name: /^Draft / })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Scout Prospect 1" }));
    expect(mocked.scout).toHaveBeenCalledWith(1);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("lets the franchise pick when it's on the clock", async () => {
    mocked.draftPick.mockResolvedValue({ season: live.season, picks: [] });
    render(<DraftView draft={live} team={team} leagueId={4} />);
    expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("You're on the clock: round 1, pick 3");
    expect(screen.getByRole("region", { name: "Picks made" })).toHaveTextContent("Second Pick");
    expect(screen.getByRole("region", { name: "Your picks" })).toHaveTextContent("R1 #3");
    await userEvent.click(screen.getByRole("button", { name: "Draft Prospect 1" }));
    expect(mocked.draftPick).toHaveBeenCalledWith(4, 1);
  });

  it("waits while another team is on the clock", () => {
    render(<DraftView draft={{ ...live, on_the_clock: 2, my_next_pick: 3 }} team={team} leagueId={4} />);
    expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent(
      `On the clock: ${opponent.full_name} (#2). Your next pick: #3.`);
    expect(screen.queryByRole("button", { name: /^Draft / })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sim to my pick" })).toBeInTheDocument();
  });

  it("offers an auto-cut when the draft leaves the roster over 53", async () => {
    mocked.cutDown.mockResolvedValue([]);
    render(<DraftView draft={{ ...live, status: "complete", on_the_clock: null, roster_count: 57,
      season: { ...season, phase: "preseason" } }} team={team} leagueId={4} />);
    expect(screen.getByRole("region", { name: "Roster cut-down" })).toHaveTextContent("cut 4");
    await userEvent.click(screen.getByRole("button", { name: "Auto-cut to 53" }));
    expect(mocked.cutDown).toHaveBeenCalledWith(team.id);
  });
});
