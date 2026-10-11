import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { HistoryOut } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { HistoryView } from "./HistoryView";

const history: HistoryOut = {
  seasons: [
    { season_id: 2, year: 2027, phase: "regular_season", complete: false, champion: null,
      runner_up: null, awards: [], franchise_record: { wins: 3, losses: 1, ties: 0 },
      franchise_result: "Season in progress" },
    { season_id: 1, year: 2026, phase: "offseason", complete: true, champion: team,
      runner_up: opponent, franchise_record: { wins: 13, losses: 4, ties: 0 },
      franchise_result: "Won the championship",
      awards: [{ award: "mvp", label: "Most Valuable Player", year: 2026, player_id: 7,
        name: "Keegan Quarles", position: "QB", team, summary: "4,512 pass yds · 33 TD · 9 INT" }] },
  ],
  records: [{ key: "passing_yards", label: "Passing yards",
    single_season: [{ player_id: 7, name: "Keegan Quarles", position: "QB", team: "HFD", year: 2026,
      value: 4512, games: 17, retired: false }],
    career: [{ player_id: 9, name: "Old Gunslinger", position: "QB", team: null, year: null,
      value: 30120, games: 140, retired: true }] }],
};

describe("HistoryView", () => {
  it("lists seasons with champions, awards, and the franchise's result", () => {
    render(<HistoryView history={history} team={team} league="Dynasty Football League" />);
    expect(screen.getByText("2 seasons · 1 Ironclads championship")).toBeInTheDocument();
    const finished = screen.getByRole("article", { name: "2026 season" });
    expect(finished).toHaveTextContent("Champion");
    expect(finished).toHaveTextContent(`over ${opponent.full_name}`);
    expect(within(finished).getByLabelText("Your season")).toHaveTextContent("13-4Won the championship");
    expect(within(finished).getByRole("list", { name: "2026 awards" })).toHaveTextContent(
      "Most Valuable PlayerQBKeegan QuarlesHFD4,512 pass yds");
    expect(screen.getByRole("article", { name: "2027 season" })).toHaveTextContent("In progress");
  });

  it("switches between single-season and career records", async () => {
    render(<HistoryView history={history} team={team} league="DFL" />);
    const passing = screen.getByRole("group", { name: "Passing yards" });
    expect(passing).toHaveTextContent("Keegan Quarles20264,512");
    await userEvent.click(screen.getByRole("tab", { name: "Career" }));
    expect(passing).toHaveTextContent("Old Gunslingerret.140 G30,120");
  });
});
