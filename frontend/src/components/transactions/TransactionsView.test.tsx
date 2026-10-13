import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Transaction } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { TransactionsView } from "./TransactionsView";

const trade = (overrides: Partial<Transaction>): Transaction => ({
  id: 1, team, partner: opponent, year: 2027, season_phase: "regular_season", week: 9,
  sent: [{ kind: "pick", id: 5, label: "2028 round 1" }],
  received: [{ kind: "player", id: 7, label: "WR Ari Vance (88)" }],
  reversed: false, between: "ai", ...overrides,
});

describe("TransactionsView", () => {
  it("lists a season's trades and who made them", () => {
    render(<TransactionsView year={2027} firstYear={2026} currentYear={2027} trades={[
      trade({}), trade({ id: 2, between: "manager_and_ai", season_phase: "preseason", reversed: true }),
    ]} />);
    const items = within(screen.getByRole("list", { name: "Trades" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Between AI teams");
    expect(items[0]).toHaveTextContent("Week 9");
    expect(items[0]).toHaveTextContent(`The ${team.nickname} sent 2028 round 1 for WR Ari Vance (88)`);
    expect(items[1]).toHaveTextContent("A manager and the AI");
    expect(items[1]).toHaveTextContent("Reversed");
    expect(items[1]).toHaveTextContent("Preseason");
    const seasons = screen.getByRole("navigation", { name: "Seasons" });
    expect(within(seasons).getByRole("link", { name: "← 2026" })).toHaveAttribute("href", "/transactions?year=2026");
    expect(within(seasons).queryByRole("link", { name: /2028/ })).not.toBeInTheDocument();
  });

  it("says when a season had none", () => {
    render(<TransactionsView year={2026} firstYear={2026} currentYear={2027} trades={[]} />);
    expect(screen.getByText("No trades in 2026.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2027 →" })).toBeInTheDocument();
  });
});
