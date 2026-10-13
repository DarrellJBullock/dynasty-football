import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { Finances } from "@/lib/types";
import { team } from "@/test/fixtures";
import { FinancesView } from "./FinancesView";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { setTicketPrice: vi.fn() } };
});
const mocked = vi.mocked(api);

const finances: Finances = {
  team, season_year: 2026, market: "medium", capacity: 68_000, ticket_price: "normal",
  prices: [{ price: "low", label: "Low", seat: 88 }, { price: "normal", label: "Normal", seat: 110 },
    { price: "high", label: "High", seat: 138 }],
  price_locked: null, share: 0.5,
  gates: [{ game_id: 3, week: 2, playoff: false, opponent: "ABQ", fan_mood: 54, attendance: 61_200,
    capacity: 68_000, price: 110, revenue: 6_732_000 }],
  revenue: [{ label: "Tickets", amount: 6_732_000 }, { label: "Media", amount: 127_500_000 }],
  expenses: [{ label: "Players", amount: 120_000_000 }],
  total_revenue: 134_232_000, total_expenses: 120_000_000, profit: 14_232_000,
  projected_profit: -3_000_000,
  history: [{ year: 2025, revenue: 300_000_000, expenses: 280_000_000, profit: 20_000_000 }],
};

beforeEach(() => vi.clearAllMocks());

describe("FinancesView", () => {
  it("shows the season's money, the gates and past seasons", () => {
    render(<FinancesView initial={finances} canSetPrice />);
    expect(screen.getByRole("region", { name: "Profit so far" })).toHaveTextContent("+$14.2M");
    expect(screen.getByRole("region", { name: "At this pace" })).toHaveTextContent("−$3.0M");
    expect(screen.getByRole("region", { name: "Revenue so far" })).toHaveTextContent("50% of the regular season played");
    expect(screen.getByRole("row", { name: /Week 2 vs ABQ/ })).toHaveTextContent("61,200 (90%)");
    expect(screen.getByRole("row", { name: /2025/ })).toHaveTextContent("+$20.0M");
  });

  it("sets the ticket price between seasons", async () => {
    mocked.setTicketPrice.mockResolvedValue({ ...finances, ticket_price: "low" });
    render(<FinancesView initial={finances} canSetPrice />);
    const prices = screen.getByRole("radiogroup", { name: "Ticket price" });
    expect(within(prices).getByRole("radio", { name: /Normal/ })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(within(prices).getByRole("radio", { name: /Low/ }));
    expect(mocked.setTicketPrice).toHaveBeenCalledWith(team.id, "low");
    expect(await within(prices).findByRole("radio", { name: /Low/ })).toHaveAttribute("aria-checked", "true");
    expect(refresh).toHaveBeenCalled();
  });

  it("locks the price during the season", () => {
    render(<FinancesView initial={{ ...finances, price_locked: "Ticket prices are set before the season." }}
      canSetPrice />);
    expect(screen.getByText("Ticket prices are set before the season.")).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });

  it("says when no home game has been played", () => {
    render(<FinancesView initial={{ ...finances, gates: [], history: [] }} canSetPrice />);
    expect(screen.getByText("No home game played yet this season.")).toBeInTheDocument();
    expect(screen.queryByText("Past seasons")).not.toBeInTheDocument();
  });
});
