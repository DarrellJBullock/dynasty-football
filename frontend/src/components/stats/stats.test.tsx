import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { LeaderCategory, PlayerSeasonStats, TeamSeasonRow } from "@/lib/types";
import { groupsFor, STAT_GROUPS } from "@/lib/stats";
import { makePlayerDetail, opponent, team } from "@/test/fixtures";
import { LeaderCards, LeaderTable } from "./LeadersView";
import { PlayerView } from "./PlayerView";
import { TeamStatsTable } from "./TeamStatsTable";

const passing: LeaderCategory = {
  key: "passing_yards", label: "Passing yards", leaders: [
    { player_id: 1, name: "Keegan Quarles", position: "QB", team, games: 2, value: 727,
      stats: { pass_cmp: 55, pass_att: 90, pass_td: 3, pass_int: 1 } },
    { player_id: 2, name: "Blake Monroe", position: "QB", team: opponent, games: 2, value: 650,
      stats: { pass_cmp: 50, pass_att: 80, pass_td: 4, pass_int: 2 } },
  ],
};

describe("stat groups", () => {
  it("picks the groups a player's stats touch", () => {
    expect(groupsFor({ pass_att: 30, rush_att: 2 }).map((g) => g.title)).toEqual(["Passing", "Rushing"]);
    expect(groupsFor({ tackles: 5 }).map((g) => g.title)).toEqual(["Defense"]);
    expect(groupsFor({})).toEqual([]);
  });

  it("formats columns safely when stats are missing", () => {
    const passingGroup = STAT_GROUPS[0];
    expect(passingGroup.columns.map(([, v]) => v({ pass_att: 10 }))).toEqual(["0/10", 0, 0, 0, 0]);
  });
});

describe("leaders", () => {
  it("shows top players per category with links and the user's team highlighted", () => {
    render(<LeaderCards categories={[passing, { key: "sacks", label: "Sacks", leaders: [] }]} teamId={team.id} />);
    const card = screen.getByRole("region", { name: "Passing yards" });
    const link = within(card).getByRole("link", { name: "Keegan Quarles" });
    expect(link).toHaveAttribute("href", "/players/1");
    expect(link.closest("li")).toHaveClass("bg-gold/[0.07]");
    expect(within(card).getByRole("link", { name: "Top 25 →" })).toHaveAttribute("href", "/stats?category=passing_yards");
    expect(within(screen.getByRole("region", { name: "Sacks" })).getByText("No games played yet.")).toBeInTheDocument();
  });

  it("shows a full category with supporting columns", () => {
    render(<LeaderTable category={passing} teamId={team.id} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
      .toEqual(["#", "Player", "Team", "G", "Passing yards", "CMP", "ATT", "TD", "INT"]);
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent(/Keegan Quarles\s*QB.*727/);
  });
});

function teamRow(overrides: Partial<TeamSeasonRow>): TeamSeasonRow {
  return { team, games: 2, wins: 1, losses: 1, ties: 0, points_for: 50, points_against: 40,
    total_yds: 700, pass_yds: 450, rush_yds: 250, first_downs: 40, turnovers: 3, sacks_allowed: 4,
    penalties: 10, penalty_yds: 80, time_of_possession: 3600, third_down_att: 26, third_down_conv: 11,
    yds_allowed: 650, pass_yds_allowed: 400, rush_yds_allowed: 250, takeaways: 4, sacks: 5, ...overrides };
}

describe("TeamStatsTable", () => {
  const rows = [
    teamRow({}),
    teamRow({ team: opponent, points_for: 70, points_against: 20, turnovers: 1 }),
  ];
  // The crest SVG also contributes its abbreviation, so compare by team name suffix.
  const names = () => screen.getAllByRole("row").slice(1)
    .map((r) => within(r).getAllByRole("cell")[1].textContent!.replace(/^(HFD|ABQ)/, ""));

  it("sorts by points per game, then any column", async () => {
    render(<TeamStatsTable rows={rows} teamId={team.id} />);
    expect(names()).toEqual(["Albuquerque Roadrunners", "Hartford Ironclads"]);
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("35.0");

    // Points allowed: lower is better, so the first click sorts ascending.
    await userEvent.click(screen.getByRole("button", { name: "PA/G" }));
    expect(names()).toEqual(["Albuquerque Roadrunners", "Hartford Ironclads"]);
    await userEvent.click(screen.getByRole("button", { name: /PA\/G/ }));
    expect(names()).toEqual(["Hartford Ironclads", "Albuquerque Roadrunners"]);
  });

  it("shows dashes before any games", () => {
    render(<TeamStatsTable rows={[teamRow({ games: 0 })]} teamId={team.id} />);
    expect(screen.getAllByText("–").length).toBeGreaterThan(0);
  });
});

describe("PlayerView", () => {
  const stats: PlayerSeasonStats = {
    player: makePlayerDetail({ first_name: "Keegan", last_name: "Quarles", full_name: "Keegan Quarles", position: "QB" }),
    team, season: { id: 1, year: 2026, phase: "regular_season", current_week: 3, weeks: 17, regular_season_complete: false, next_round: null, champion: null },
    games: 2, totals: { pass_att: 60, pass_cmp: 40, pass_yds: 411, pass_td: 5, rush_att: 5, rush_yds: -4 },
    game_log: [
      { game_id: 7, week: 1, opponent, home: true, result: "W 28-22", stats: { pass_att: 29, pass_cmp: 20, pass_yds: 215 } },
      { game_id: 8, week: 2, opponent, home: false, result: "L 30-36 OT", stats: { pass_att: 31, pass_cmp: 20, pass_yds: 196 } },
    ],
  };

  it("shows bio, season totals for relevant groups, and the game log", () => {
    render(<PlayerView player={{ ...makePlayerDetail({ position: "QB" }), full_name: "Keegan Quarles" }} stats={stats} />);
    expect(screen.getByRole("heading", { level: 1, name: "Keegan Quarles" })).toBeInTheDocument();
    const totals = screen.getByRole("region", { name: "Season totals" });
    expect(totals).toHaveTextContent("2026 season · 2 games");
    expect(totals).toHaveTextContent("40/60");
    expect(within(totals).queryByText("Defense")).not.toBeInTheDocument();
    const log = screen.getByRole("region", { name: "Game log" });
    expect(within(log).getByRole("link", { name: "L 30-36 OT" })).toHaveAttribute("href", "/games/8");
    expect(within(log).getAllByRole("row")).toHaveLength(3);
  });

  it("handles a player with no games", () => {
    render(<PlayerView player={makePlayerDetail({})} stats={{ ...stats, games: 0, totals: {}, game_log: [], team: null }} />);
    expect(screen.getByText("No stats yet this season.")).toBeInTheDocument();
    expect(screen.getByText(/Free agent/)).toBeInTheDocument();
  });

  it("marks retired players", () => {
    render(<PlayerView player={makePlayerDetail({ retired_year: 2026 })} stats={{ ...stats, games: 0, totals: {}, game_log: [], team: null }} />);
    expect(screen.getByText(/Retired after 2026/)).toBeInTheDocument();
  });
});
