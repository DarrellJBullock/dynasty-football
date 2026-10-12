import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DynastyReport, SeasonHistory } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { DynastyReportView } from "./DynastyReportView";

function season(year: number, champion: typeof team | null, wins: number): SeasonHistory {
  return { season_id: year, year, phase: "offseason", complete: true, champion, runner_up: null,
    awards: [], franchise_record: { wins, losses: 17 - wins, ties: 0 },
    franchise_result: champion?.id === team.id ? "Won the championship" : "Missed the playoffs" };
}

const report: DynastyReport = {
  from_year: 2026, to_year: 2027,
  seasons: [
    { season: season(2026, team, 13), offseason: {
      from_year: 2026, year: 2027, retired: [], departed: [], re_signed: [], signed: [],
      rookies: [], risers: [], decliners: [], league_retirements: [] } },
    { season: season(2027, opponent, 6), offseason: null },
  ],
};

describe("DynastyReportView", () => {
  it("sums up the seasons and shows each one with the offseason after it", () => {
    render(<DynastyReportView report={report} team={team} league="Dynasty Football League" />);
    expect(screen.getByRole("heading", { level: 1, name: "Dynasty report" })).toBeInTheDocument();
    expect(screen.getByText(/2026–2027 · 2 seasons · Ironclads 19–15 · 1 championship/))
      .toBeInTheDocument();
    expect(screen.getByRole("article", { name: "2026 season" })).toHaveTextContent("Won the championship");
    expect(screen.getByRole("article", { name: "2027 season" })).toHaveTextContent("Missed the playoffs");
    // The offseason after 2026 (none yet after the latest season).
    expect(screen.getAllByRole("region", { name: "Offseason recap" })).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Offseason recap" })).toHaveTextContent("Ready for 2027");
    expect(screen.getByRole("link", { name: "History →" })).toHaveAttribute("href", "/history");
  });

  it("says so when the span has no finished seasons", () => {
    render(<DynastyReportView report={{ from_year: 2030, to_year: 2030, seasons: [] }} team={team} league="DFL" />);
    expect(screen.getByText("No finished seasons in 2030.")).toBeInTheDocument();
  });
});
