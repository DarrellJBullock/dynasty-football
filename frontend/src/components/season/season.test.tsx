import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { Game, GameDetail, PlayOut, Season } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { GameView } from "./GameView";
import { ScheduleView } from "./ScheduleView";
import { SimControls } from "./SimControls";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { simulate: vi.fn() } };
});
const mocked = vi.mocked(api);

const season: Season = { id: 5, year: 2026, phase: "regular_season", current_week: 3, weeks: 17,
  regular_season_complete: false };

function game(overrides: Partial<Game> = {}): Game {
  return { id: 11, week: 3, home: team, away: opponent, home_score: 26, away_score: 17,
    status: "final", overtime: false, ...overrides };
}

beforeEach(() => vi.clearAllMocks());

describe("SimControls", () => {
  it("sims the next week, shows the franchise result, and refreshes", async () => {
    mocked.simulate.mockResolvedValue({ weeks_simulated: 1, games_simulated: 16,
      season: { ...season, current_week: 4 }, franchise_games: [game()] });
    render(<SimControls season={season} teamId={team.id} />);

    await userEvent.click(screen.getByRole("button", { name: "Sim week 3" }));
    expect(mocked.simulate).toHaveBeenCalledWith(5, "next_week");
    const result = await screen.findByRole("status");
    expect(result).toHaveTextContent("Week 3: W 26-17 vs Roadrunners");
    expect(result).toHaveAttribute("href", "/games/11");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("asks for confirmation before simming the rest of the season", async () => {
    mocked.simulate.mockResolvedValue({ weeks_simulated: 15, games_simulated: 240,
      season: { ...season, current_week: 18, regular_season_complete: true },
      franchise_games: [game({ week: 17 })] });
    render(<SimControls season={season} teamId={team.id} />);

    await userEvent.click(screen.getByRole("button", { name: "Sim to end of season" }));
    expect(mocked.simulate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim weeks 3–17" }));
    expect(mocked.simulate).toHaveBeenCalledWith(5, "end_of_regular_season");
    expect(await screen.findByRole("status")).toHaveTextContent("Simulated 15 weeks");
  });

  it("shows errors", async () => {
    mocked.simulate.mockRejectedValue(new ApiError(409, "The regular season is complete."));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim week 3" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("complete");
  });

  it("says when the regular season is over", () => {
    render(<SimControls season={{ ...season, current_week: 18, regular_season_complete: true }} teamId={team.id} />);
    expect(screen.getByText("Regular season complete")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("ScheduleView", () => {
  it("lists the week with the franchise game first and week links", () => {
    const other = { ...opponent, id: 7, full_name: "Norfolk Squall", nickname: "Squall", abbreviation: "NOR" };
    const third = { ...opponent, id: 8, full_name: "Tulsa Twisters", nickname: "Twisters", abbreviation: "TUL" };
    render(<ScheduleView teamId={team.id} schedule={{ season, week: 2, games: [
      game({ id: 1, week: 2, home: other, away: third }),
      game({ id: 2, week: 2 }),
    ] }} />);

    const weeks = screen.getByRole("navigation", { name: "Weeks" });
    expect(within(weeks).getAllByRole("link")).toHaveLength(17);
    expect(within(weeks).getByRole("link", { name: "Wk 2" })).toHaveAttribute("aria-current", "page");
    const cards = within(screen.getByRole("region", { name: "Week 2 games" })).getAllByRole("link");
    expect(cards[0]).toHaveAccessibleName("Albuquerque Roadrunners at Hartford Ironclads");
    expect(cards[0]).toHaveAttribute("href", "/games/2");
    expect(cards[0]).toHaveTextContent("26");
  });
});

function play(n: number, overrides: Partial<PlayOut> = {}): PlayOut {
  return { n, quarter: 1, clock: "15:00", offense: "HFD", down: 1, distance: 10, spot: "HFD 25",
    type: "run", text: `Play ${n}.`, home_score: 0, away_score: 0, scoring: false, ...overrides };
}

const detail: GameDetail = {
  game: game(),
  season_year: 2026,
  line_score: { home: [7, 10, 3, 6], away: [0, 7, 10, 0] },
  team_stats: {
    home: { total_yds: 412, pass_yds: 250, pass_cmp: 20, pass_att: 30, rush_yds: 162, rush_att: 30,
      first_downs: 22, third_down_conv: 6, third_down_att: 12, turnovers: 1, sacks_allowed: 2,
      penalties: 4, penalty_yds: 30, time_of_possession: 1900 },
    away: { total_yds: 300, pass_yds: 200, pass_cmp: 18, pass_att: 31, rush_yds: 100, rush_att: 22,
      first_downs: 17, third_down_conv: 4, third_down_att: 13, turnovers: 2, sacks_allowed: 3,
      penalties: 6, penalty_yds: 45, time_of_possession: 1700 },
  },
  players: [
    { player_id: 1, team_id: team.id, name: "Keegan Quarles", position: "QB",
      stats: { pass_att: 30, pass_cmp: 20, pass_yds: 250, pass_td: 2 } },
    { player_id: 2, team_id: opponent.id, name: "Ben Monroe", position: "QB",
      stats: { pass_att: 31, pass_cmp: 18, pass_yds: 200, pass_int: 1 } },
  ],
  scoring_plays: [play(9, { text: "Nash runs for 3 yards. TOUCHDOWN.", scoring: true, home_score: 6 })],
  plays: [play(1), play(2), play(9, { quarter: 2, text: "Nash runs for 3 yards. TOUCHDOWN.", scoring: true })],
};

describe("GameView", () => {
  it("shows the scoreboard, line score, team stats, box score and play-by-play", () => {
    render(<GameView detail={detail} />);
    expect(screen.getByTestId("score-home")).toHaveTextContent("26");
    expect(screen.getByText("Final")).toBeInTheDocument();
    const line = screen.getByRole("region", { name: "Line score" });
    expect(within(line).getAllByRole("row")[2]).toHaveTextContent("HFD7103626");
    const stats = screen.getByRole("region", { name: "Team stats" });
    expect(within(stats).getByText("31:40")).toBeInTheDocument(); // 1900 s of possession
    expect(screen.getByRole("table", { name: "HFD passing" })).toHaveTextContent("Keegan Quarles");
    expect(screen.getByRole("table", { name: "ABQ passing" })).toHaveTextContent("18/31");
    expect(screen.getByRole("region", { name: "Scoring summary" })).toHaveTextContent("TOUCHDOWN");
    expect(screen.getByRole("list", { name: "Quarter 1" })).toHaveTextContent("HFD 1st&10");
    expect(screen.getByText("Quarter 2")).toBeInTheDocument();
  });

  it("explains an unplayed game", () => {
    render(<GameView detail={{ ...detail, game: game({ status: "scheduled", home_score: null, away_score: null }),
      players: [], plays: [], scoring_plays: [], line_score: { home: [], away: [] }, team_stats: {} }} />);
    expect(screen.getByText("Not played yet")).toBeInTheDocument();
    expect(screen.getByText(/hasn't been played yet/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Line score" })).not.toBeInTheDocument();
  });
});

describe("routing helpers", () => {
  it("refresh is only called after a successful sim", async () => {
    mocked.simulate.mockRejectedValue(new Error("boom"));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim week 3" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(router.refresh).not.toHaveBeenCalled();
  });
});
