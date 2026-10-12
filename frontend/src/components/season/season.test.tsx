import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { Game, GameDetail, Job, PlayOut, Season } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { GameView } from "./GameView";
import { ScheduleView } from "./ScheduleView";
import { SimControls } from "./SimControls";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { simulate: vi.fn(), playFreeAgency: vi.fn(), playDraft: vi.fn(),
    startJob: vi.fn(), job: vi.fn(), cancelJob: vi.fn() } };
});
const mocked = vi.mocked(api);

const season: Season = { id: 5, league_id: 1, year: 2026, phase: "regular_season", current_week: 3, weeks: 17,
  regular_season_complete: false,
  next_round: null, champion: null };

function game(overrides: Partial<Game> = {}): Game {
  return { id: 11, week: 3, home: team, away: opponent, home_score: 26, away_score: 17,
    status: "final", overtime: false, stage: "regular", round_name: null, neutral_site: false,
    ...overrides };
}

function job(overrides: Partial<Job> = {}): Job {
  return { id: 40, league_id: 1, kind: "sim_regular_season", status: "queued", progress: 0,
    total: 15, label: "Simulating the season", cancellable: true, cancel_requested: false,
    result: null, error: null, ...overrides };
}

const POLL = { timeout: 3000 }; // the progress is polled every half second

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

  it("asks for confirmation, then sims the rest of the season in the background", async () => {
    mocked.startJob.mockResolvedValue(job());
    mocked.job.mockResolvedValueOnce(job({ status: "running", progress: 2, label: "Week 4 of 17" }))
      .mockResolvedValue(job({ status: "done", progress: 15, label: "Week 17 of 17",
        result: { weeks_simulated: 15, games_simulated: 240,
          season: { ...season, current_week: 18, regular_season_complete: true },
          franchise_games: [game({ week: 17 })] } }));
    render(<SimControls season={season} teamId={team.id} />);

    await userEvent.click(screen.getByRole("button", { name: "Sim to end of season" }));
    expect(mocked.startJob).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim weeks 3–17" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "sim_regular_season");
    const bar = screen.getByRole("progressbar", { name: "Simulation progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "15");
    expect(screen.getByRole("button", { name: "Sim week 3" })).toBeDisabled();
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuenow", "2"), POLL);
    expect(screen.getByText("Week 4 of 17")).toBeInTheDocument();

    expect(await screen.findByRole("status", {}, POLL)).toHaveTextContent(
      "Simulated 15 weeks · Last game: W 26-17 vs Roadrunners");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(router.refresh).toHaveBeenCalledTimes(1);
  });

  it("stops a background sim after the week it's on", async () => {
    mocked.startJob.mockResolvedValue(job({ status: "running", progress: 1, label: "Week 3 of 17" }));
    mocked.cancelJob.mockResolvedValue(job({ status: "running", progress: 1, label: "Week 3 of 17",
      cancel_requested: true }));
    mocked.job.mockResolvedValue(job({ status: "cancelled", progress: 2, label: "Week 4 of 17",
      cancel_requested: true }));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim to end of season" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim weeks 3–17" }));

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(mocked.cancelJob).toHaveBeenCalledWith(40);
    expect(screen.getByText("Stopping after this one…")).toBeInTheDocument();
    expect(await screen.findByRole("status", {}, POLL)).toHaveTextContent("Stopped after Week 4 of 17");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("shows why a background sim failed, or couldn't start", async () => {
    mocked.startJob.mockResolvedValueOnce(job({ status: "failed",
      error: "Cut your roster to 53 (it has 60) before the season starts." }));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim to end of season" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim weeks 3–17" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cut your roster to 53");

    mocked.startJob.mockRejectedValueOnce(new ApiError(409, "A simulation is already running in this league."));
    await userEvent.click(screen.getByRole("button", { name: "Sim to end of season" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim weeks 3–17" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already running");
  });

  it("picks up a sim already running in the league", async () => {
    mocked.job.mockResolvedValue(job({ status: "done", progress: 15, result: {
      weeks_simulated: 15, games_simulated: 240, season, franchise_games: [] } }));
    render(<SimControls season={{ ...season, active_job: job({ status: "running", progress: 6,
      label: "Week 8 of 17" }) }} teamId={team.id} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "6");
    expect(screen.getByText("Week 8 of 17")).toBeInTheDocument();
    await waitFor(() => expect(router.refresh).toHaveBeenCalled(), POLL);
    expect(mocked.job).toHaveBeenCalledWith(40);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows errors", async () => {
    mocked.simulate.mockRejectedValue(new ApiError(409, "The regular season is complete."));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim week 3" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("complete");
  });

  it("sims playoff rounds once the regular season is over", async () => {
    const playoffs = { ...season, phase: "playoffs", current_week: 18, regular_season_complete: true,
      next_round: "Wild Card" };
    mocked.simulate.mockResolvedValue({ weeks_simulated: 1, games_simulated: 6,
      season: { ...playoffs, next_round: "Divisional" },
      franchise_games: [game({ week: 18, stage: "playoff", round_name: "Wild Card" })] });
    render(<SimControls season={playoffs} teamId={team.id} />);

    expect(screen.getByRole("link", { name: "Bracket →" })).toHaveAttribute("href", "/playoffs");
    await userEvent.click(screen.getByRole("button", { name: "Sim Wild Card" }));
    expect(mocked.simulate).toHaveBeenCalledWith(5, "next_week");
    expect(await screen.findByRole("status")).toHaveTextContent("Wild Card: W 26-17 vs Roadrunners");

    mocked.startJob.mockResolvedValue(job({ kind: "sim_playoffs", status: "running", total: 3 }));
    await userEvent.click(screen.getByRole("button", { name: "Sim rest of playoffs" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim to a champion" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "sim_playoffs");
  });

  it("shows the champion and starts free agency after confirmation", async () => {
    mocked.startJob.mockResolvedValue(job({ kind: "advance_offseason", status: "done", total: 1,
      progress: 1, cancellable: false, result: { ...season, id: 6, year: 2027, phase: "free_agency" } }));
    render(<SimControls season={{ ...season, phase: "offseason", current_week: 21,
      regular_season_complete: true, champion: opponent }} teamId={team.id} />);
    expect(screen.getByText(/2026 champion: Albuquerque Roadrunners/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Start free agency" }));
    expect(mocked.startJob).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm: run the offseason" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "advance_offseason");
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });
});

describe("SimControls in free agency", () => {
  const market = { ...season, id: 6, year: 2027, phase: "free_agency", current_week: 1,
    free_agency_day: 2 };

  it("plays a market day and reports signings", async () => {
    mocked.playFreeAgency.mockResolvedValue({ season: { ...market, free_agency_day: 3 },
      signings: [], mine: [] });
    render(<SimControls season={market} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Play free agency day 2" }));
    expect(mocked.playFreeAgency).toHaveBeenCalledWith(6, "next_day");
    expect(await screen.findByRole("status")).toHaveTextContent("Day 2: 0 signing(s) league-wide · none of yours");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("finishes the market in the background after confirmation", async () => {
    mocked.startJob.mockResolvedValue(job({ kind: "finish_free_agency", total: 4 }));
    mocked.job.mockResolvedValue(job({ kind: "finish_free_agency", status: "done", total: 4,
      progress: 4, label: "Day 5 of 5",
      result: { season: { ...market, phase: "draft" }, signings: [{}, {}], mine: [] } }));
    render(<SimControls season={market} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Finish free agency" }));
    expect(mocked.startJob).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm: finish free agency" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "finish_free_agency");
    expect(within(screen.getByRole("group", { name: "Free agency" })).getByRole("progressbar"))
      .toBeInTheDocument();
    expect(await screen.findByRole("status", {}, POLL)).toHaveTextContent(
      "Free agency: 2 signing(s) league-wide · none of yours");
    expect(router.refresh).toHaveBeenCalled();
  });
});

describe("Sim ahead", () => {
  const ahead = (overrides: Partial<Job> = {}) => job({ kind: "sim_seasons", params: { seasons: 5 },
    total: 140, label: "Simming ahead", ...overrides });

  it("sims several seasons ahead and links to the Dynasty report", async () => {
    mocked.startJob.mockResolvedValue(ahead({ status: "running", progress: 3,
      label: "Season 1 of 5 · 2026 · Week 5 of 17" }));
    mocked.job.mockResolvedValue(ahead({ status: "done", progress: 140,
      result: { from_year: 2026, to_year: 2030, seasons: 5 } }));
    render(<SimControls season={season} teamId={team.id} />);

    await userEvent.click(screen.getByRole("button", { name: "Sim ahead…" }));
    const form = screen.getByRole("group", { name: "Sim ahead" });
    expect(form).toHaveTextContent("The AI runs your team through each offseason.");
    await userEvent.selectOptions(within(form).getByLabelText("Seasons"), "5");
    await userEvent.click(within(form).getByRole("button", { name: "Confirm: sim ahead 5 seasons" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "sim_seasons", 5);
    expect(screen.getByText("Season 1 of 5 · 2026 · Week 5 of 17")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sim ahead…" })).not.toBeInTheDocument();

    const link = await screen.findByRole("status", {}, POLL);
    expect(link).toHaveTextContent("Simmed 5 seasons · Dynasty report, 2026–2030 →");
    expect(link).toHaveAttribute("href", "/dynasty?from=2026&to=2030");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("can start from free agency, and says where a stopped run got to", async () => {
    const market = { ...season, phase: "free_agency", free_agency_day: 2 };
    mocked.startJob.mockResolvedValue(ahead({ status: "running", params: { seasons: 2 } }));
    mocked.job.mockResolvedValue(ahead({ status: "cancelled", progress: 9,
      label: "Season 1 of 2 · 2026 · Week 5 of 17" }));
    render(<SimControls season={market} teamId={team.id} />);
    const controls = screen.getByRole("group", { name: "Free agency" });
    await userEvent.click(within(controls).getByRole("button", { name: "Sim ahead…" }));
    await userEvent.selectOptions(screen.getByLabelText("Seasons"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim ahead 2 seasons" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "sim_seasons", 2);
    expect(await screen.findByText("Stopped after Season 1 of 2 · 2026 · Week 5 of 17", {}, POLL))
      .toBeInTheDocument();
  });

  it("shows why it failed", async () => {
    mocked.startJob.mockResolvedValue(ahead({ status: "failed",
      error: "Finish the game you're coaching (or let the AI finish it) before simulating the week." }));
    render(<SimControls season={season} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim ahead…" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: sim ahead 3 seasons" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Finish the game you're coaching");
  });
});

describe("SimControls during the draft", () => {
  const drafting = { ...season, id: 6, year: 2027, phase: "draft", current_week: 1 };

  it("sims to the franchise's pick, or finishes after confirmation", async () => {
    mocked.playDraft.mockResolvedValue({ season: drafting, picks: [] });
    render(<SimControls season={drafting} teamId={team.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Sim to my pick" }));
    expect(mocked.playDraft).toHaveBeenCalledWith(6, "my_pick");
    expect(await screen.findByRole("status")).toHaveTextContent("you're on the clock");

    mocked.startJob.mockResolvedValue(job({ kind: "finish_draft", total: 1, cancellable: false }));
    mocked.job.mockResolvedValue(job({ kind: "finish_draft", status: "done", total: 1, progress: 1,
      cancellable: false, result: { season: { ...drafting, phase: "preseason" }, picks: [] } }));
    await userEvent.click(screen.getByRole("button", { name: "Finish draft" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: finish the draft (auto-pick for me)" }));
    expect(mocked.startJob).toHaveBeenCalledWith(1, "finish_draft");
    // The draft finishes as one step: no Stop.
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    expect(await screen.findByText("The draft is complete", {}, POLL)).toBeInTheDocument();
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
    expect(within(weeks).getAllByRole("link", { name: /^Wk/ })).toHaveLength(17);
    expect(within(weeks).getByRole("link", { name: "Playoffs →" })).toHaveAttribute("href", "/playoffs");
    expect(within(weeks).getByRole("link", { name: "Wk 2" })).toHaveAttribute("aria-current", "page");
    const region = screen.getByRole("region", { name: "Week 2 games" });
    const cards = within(region).getAllByRole("listitem");
    const ours = within(cards[0]).getByRole("link", { name: "Albuquerque Roadrunners at Hartford Ironclads" });
    expect(ours).toHaveAttribute("href", "/games/2");
    expect(cards[0]).toHaveTextContent("26");
    // Played games can be watched; nothing to coach in a week that's over.
    expect(within(cards[0]).getByRole("link", { name: "Watch Albuquerque Roadrunners at Hartford Ironclads" }))
      .toHaveAttribute("href", "/games/2/watch?auto=1");
    expect(within(region).queryByRole("link", { name: /^Coach/ })).not.toBeInTheDocument();
  });

  it("offers to coach the franchise's game this week, and nothing to watch yet", () => {
    render(<ScheduleView teamId={team.id} schedule={{ season, week: 3, games: [
      game({ id: 4, week: 3, status: "scheduled", home_score: null, away_score: null }),
    ] }} />);
    const card = within(screen.getByRole("region", { name: "Week 3 games" })).getByRole("listitem");
    expect(within(card).getByRole("link", { name: "Coach Albuquerque Roadrunners at Hartford Ironclads" }))
      .toHaveAttribute("href", "/coach");
    expect(within(card).queryByRole("link", { name: /^Watch/ })).not.toBeInTheDocument();
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
  plays: [play(1, { play_name: "Smash", defense_name: "Cover 2" }), play(2),
    play(9, { quarter: 2, text: "Nash runs for 3 yards. TOUCHDOWN.", scoring: true })],
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
    expect(screen.getByRole("list", { name: "Quarter 1" })).toHaveTextContent("Smash vs Cover 2");
    expect(screen.getByText("Quarter 2")).toBeInTheDocument();
  });

  it("explains an older game whose play-by-play was trimmed, with nothing to watch", () => {
    render(<GameView detail={{ ...detail, log_compacted: true }} />);
    const panel = screen.getByRole("region", { name: "Play-by-play" });
    expect(panel).toHaveTextContent("This game keeps its scoring plays and injuries.");
    expect(within(panel).queryByRole("link", { name: "Watch in 3D" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Line score" })).toBeInTheDocument();
  });

  it("links the game and each play to the 3D viewer", () => {
    render(<GameView detail={detail} />);
    const id = detail.game.id;
    expect(screen.getByRole("link", { name: "Watch in 3D" })).toHaveAttribute("href", `/games/${id}/watch?auto=1`);
    expect(screen.getByRole("link", { name: "Highlights" }))
      .toHaveAttribute("href", `/games/${id}/watch?highlights=1&auto=1`);
    expect(screen.getByRole("link", { name: "Watch play 9" }))
      .toHaveAttribute("href", `/games/${id}/watch?play=9`);
  });

  it("lists injuries from the game", () => {
    const { rerender } = render(<GameView detail={detail} />);
    expect(screen.queryByRole("list", { name: "Injuries" })).not.toBeInTheDocument();
    rerender(<GameView detail={{ ...detail, injuries: [
      { player_id: 31, team_id: opponent.id, name: "Rod Banks", position: "WR", injury: "Torn ACL",
        weeks: 99, quarter: 3, clock: "4:12" },
    ] }} />);
    const list = screen.getByRole("list", { name: "Injuries" });
    expect(list).toHaveTextContent("Q3 4:12");
    expect(list).toHaveTextContent("ABQ");
    expect(list).toHaveTextContent("Torn ACL");
    expect(list).toHaveTextContent("Out for the season");
    expect(within(list).getByRole("link", { name: /Rod Banks/ })).toHaveAttribute("href", "/players/31");
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
