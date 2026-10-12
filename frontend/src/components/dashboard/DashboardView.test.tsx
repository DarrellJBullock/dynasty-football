import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { dashboard, makePlayer, team } from "@/test/fixtures";
import { DashboardView } from "./DashboardView";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

// WebGL isn't available in jsdom; the 3D preview is exercised in the browser.
vi.mock("@/components/field/FieldPreviewLoader", () => ({
  FieldPreviewLoader: () => <div data-testid="field-preview" />,
}));

describe("DashboardView", () => {
  it("shows the franchise identity and team rating", () => {
    render(<DashboardView data={dashboard} />);
    expect(screen.getByRole("heading", { level: 1, name: "Ironclads" })).toBeInTheDocument();
    expect(screen.getByText(/Ironclads Dynasty · 2026 Preseason/)).toBeInTheDocument();
    expect(screen.getByTitle(/79 overall/)).toBeInTheDocument();
    expect(screen.getByTestId("field-preview")).toBeInTheDocument();
  });

  it("shows the next opponent with home/away", () => {
    render(<DashboardView data={dashboard} />);
    const card = screen.getByRole("region", { name: "Next game" });
    expect(within(card).getByText("Albuquerque Roadrunners")).toBeInTheDocument();
    expect(within(card).getByText("Week 1 · Home")).toBeInTheDocument();
    const coach = within(card).getByRole("link", { name: "Coach this game" });
    expect(coach.getAttribute("href")).toMatch(/^\/games\/\d+\/coach$/);
  });

  it("shows cap space and roster count", () => {
    render(<DashboardView data={dashboard} />);
    expect(within(screen.getByRole("region", { name: "Salary cap" })).getByText("$15.3M")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Active roster" })).getByText("53")).toBeInTheDocument();
  });

  it("lists top players, standings, alerts and schedule", () => {
    render(<DashboardView data={dashboard} />);
    expect(screen.getByText("Terrell Stroud")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "ATL North standings" })).toHaveTextContent("Hartford Ironclads");
    expect(screen.getByText("21 contract(s) expire after this season.")).toBeInTheDocument();
    const schedule = screen.getByRole("region", { name: "Upcoming schedule" });
    expect(within(schedule).getByText("vs Roadrunners")).toBeInTheDocument();
    expect(within(schedule).getByText("@ Roadrunners")).toBeInTheDocument();
  });

  it("shows the injury report", () => {
    const { rerender } = render(<DashboardView data={dashboard} />);
    const panel = () => screen.getByRole("region", { name: "Injury report" });
    expect(panel()).toHaveTextContent("Everyone is healthy.");
    rerender(<DashboardView data={{ ...dashboard, injury_report: [
      makePlayer({ id: 40, full_name: "Hurt Guy", injury_status: "injured_reserve",
        injury: "High ankle sprain", injury_weeks: 5 }),
      makePlayer({ id: 41, full_name: "Sore Guy", injury_status: "questionable",
        injury: "Back spasms", injury_weeks: 0 }),
    ] }} />);
    const items = within(panel()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("IR");
    expect(items[0]).toHaveTextContent("High ankle sprain · Out 5 games");
    expect(items[1]).toHaveTextContent("Back spasms · Questionable, playing hurt");
  });

  it("shows the offseason recap before the first game", () => {
    const player = (id: number, full_name: string, overall = 70) =>
      makePlayer({ id, full_name, overall });
    const { rerender } = render(<DashboardView data={dashboard} />);
    expect(screen.queryByRole("region", { name: "Offseason recap" })).not.toBeInTheDocument();

    rerender(<DashboardView data={{ ...dashboard, offseason: {
      from_year: 2026, year: 2027,
      re_signed: [{ player: player(1, "Kept Guy", 81), salary: 12_500_000, years: 3 }],
      signed: [{ player: player(2, "New Vet"), salary: 1_200_000, years: 2 }],
      rookies: [player(3, "Young Kid", 61)],
      retired: [player(4, "Old Timer")],
      departed: [player(5, "Gone Guy")],
      risers: [{ player: player(6, "Rising Star", 77), before: 71, after: 77 }],
      decliners: [{ player: player(7, "Fading Vet", 74), before: 78, after: 74 }],
      league_retirements: [{ player: player(8, "Legend Smith", 88), team }],
    } }} />);
    const recap = screen.getByRole("region", { name: "Offseason recap" });
    expect(recap).toHaveTextContent("2026 offseason");
    expect(recap).toHaveTextContent("1 re-signed · 2 gone · 2 new");
    expect(within(recap).getByRole("group", { name: "Re-signed" })).toHaveTextContent("$12.5M × 3");
    const arrivals = within(recap).getByRole("group", { name: "New arrivals" });
    expect(arrivals).toHaveTextContent("FA · $1.2M × 2");
    expect(arrivals).toHaveTextContent("Undrafted rookie");
    expect(within(recap).getByRole("group", { name: "Gone" })).toHaveTextContent("Left in free agency");
    const development = within(recap).getByRole("group", { name: "Development" });
    expect(development).toHaveTextContent("+6");
    expect(development).toHaveTextContent("-4");
    expect(within(recap).getByRole("link", { name: "Legend Smith" })).toHaveAttribute("href", "/players/8");
  });
});
