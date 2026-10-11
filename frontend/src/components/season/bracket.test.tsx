import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Game, PlayoffsOut, Season, TeamSummary } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { BracketView } from "./BracketView";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const season: Season = { id: 5, year: 2026, phase: "playoffs", current_week: 19, weeks: 17,
  regular_season_complete: true, next_round: "Championship", champion: null };

function club(id: number, nickname: string): TeamSummary {
  return { ...opponent, id, nickname, full_name: `City ${nickname}`, abbreviation: nickname.slice(0, 3).toUpperCase() };
}
const north = club(21, "Hawks");
const south = club(22, "Owls");

function seed(t: TeamSummary, n: number, overrides = {}) {
  return { seed: n, team: t, wins: 12 - n, losses: 5 + n, ties: 0, division_winner: n === 1,
    eliminated: false, ...overrides };
}

function game(id: number, home: TeamSummary, away: TeamSummary, overrides: Partial<Game> = {}): Game {
  return { id, week: 18, home, away, home_score: 24, away_score: 10, status: "final", overtime: false,
    stage: "playoff", round_name: "Conference Championship", neutral_site: false, ...overrides };
}

const bracket: PlayoffsOut = {
  season,
  status: "in_progress",
  champion: null,
  conferences: [
    { conference: "Atlantic", seeds: [seed(team, 1), seed(north, 2, { eliminated: true })] },
    { conference: "Pacific", seeds: [seed(opponent, 1), seed(south, 2, { eliminated: true })] },
  ],
  rounds: [
    { round: 1, name: "Conference Championship", games: [
      game(31, team, north), game(32, opponent, south)] },
    { round: 2, name: "Championship", games: [
      game(33, team, opponent, { status: "scheduled", home_score: null, away_score: null,
        neutral_site: true, round_name: "Championship" })] },
  ],
};

describe("BracketView", () => {
  it("shows seeds per conference and the rounds", () => {
    render(<BracketView bracket={bracket} teamId={team.id} />);
    const atlantic = screen.getByRole("region", { name: "Atlantic seeds" });
    const rows = within(atlantic).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Hartford Ironclads");
    expect(rows[1]).toHaveAttribute("data-eliminated", "true");

    const first = screen.getByRole("group", { name: "Conference Championship" });
    expect(within(first).getAllByRole("link")).toHaveLength(2);
    expect(within(first).getByText("Atlantic")).toBeInTheDocument();
    const final = within(screen.getByRole("group", { name: "Championship" })).getByRole("link");
    expect(final).toHaveAttribute("href", "/games/33");
    expect(final).toHaveTextContent("Neutral site");
    expect(screen.getByRole("button", { name: "Sim Championship" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Champion" })).not.toBeInTheDocument();
  });

  it("labels a projected bracket and hides the rounds", () => {
    render(<BracketView bracket={{ ...bracket, status: "projected", rounds: bracket.rounds.map(
      (r) => ({ ...r, games: [] })), season: { ...season, phase: "regular_season", current_week: 9,
      regular_season_complete: false, next_round: null } }} teamId={team.id} />);
    expect(screen.getByText(/if the season ended today/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bracket" })).not.toBeInTheDocument();
  });

  it("crowns the champion", () => {
    render(<BracketView bracket={{ ...bracket, status: "complete", champion: opponent,
      season: { ...season, phase: "offseason", champion: opponent } }} teamId={team.id} />);
    expect(screen.getByRole("region", { name: "Champion" })).toHaveTextContent("Albuquerque Roadrunners");
  });
});
