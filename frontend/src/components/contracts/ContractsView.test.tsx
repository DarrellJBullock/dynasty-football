import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { TeamContracts } from "@/lib/types";
import { makePlayer, team } from "@/test/fixtures";
import { ContractsView } from "./ContractsView";

const router = { refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { reSign: vi.fn() } };
});
const mocked = vi.mocked(api);

const contract = (salary: number, end_year: number) =>
  ({ start_year: end_year - 1, years: 2, end_year, salary, signing_bonus: 0 });
const star = makePlayer({ id: 5, full_name: "Star Receiver", position: "WR", age: 27, overall: 86,
  contract: contract(9_000_000, 2026) });
const vet = makePlayer({ id: 6, full_name: "Old Guard", position: "OG", age: 33, overall: 72,
  contract: contract(2_000_000, 2026) });
const locked = makePlayer({ id: 7, full_name: "Locked Up", contract: contract(20_000_000, 2029) });

const data: TeamContracts = {
  season: { id: 5, league_id: 1, year: 2026, phase: "offseason", current_week: 21, weeks: 17,
    regular_season_complete: true, next_round: null, champion: null },
  window_open: true,
  salary_cap: 255_000_000,
  payroll: 240_000_000,
  next_year_payroll: 200_000_000,
  expiring: [
    { player: star, asking: { salary: 18_500_000, years: 3 }, re_signed: null },
    { player: vet, asking: { salary: 1_900_000, years: 1 },
      re_signed: { start_year: 2027, years: 1, end_year: 2027, salary: 1_900_000, signing_bonus: 0 } },
  ],
  players: [locked, star, vet],
};

beforeEach(() => vi.clearAllMocks());

describe("ContractsView", () => {
  it("shows the cap picture, expiring deals, and every contract", () => {
    render(<ContractsView data={data} team={team} />);
    const cap = screen.getByRole("region", { name: "Salary cap" });
    expect(cap).toHaveTextContent("Committed to 2027$200M");
    expect(cap).toHaveTextContent("2027 cap space$55.0M");
    const expiring = screen.getByRole("region", { name: "Expiring contracts" });
    expect(expiring).toHaveTextContent("1 of 2 re-signed");
    const rows = within(expiring).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("$18.5M × 3 yrs");
    expect(rows[2]).toHaveTextContent("Re-signed · $1.9M × 1");
    expect(within(screen.getByRole("region", { name: "All contracts" })).getAllByRole("row")).toHaveLength(4);
  });

  it("lists dead money and signing bonuses", () => {
    const withBonus = { ...locked, contract: { ...contract(20_000_000, 2029), signing_bonus: 24_000_000 } };
    render(<ContractsView data={{ ...data, players: [withBonus, star, vet], dead_money: [
      { player_id: 8, name: "Cut Guy", position: "WR", year: 2027, amount: 4_500_000, reason: "released" },
    ] }} team={team} />);
    const dead = screen.getByRole("region", { name: "Dead money" });
    expect(dead).toHaveTextContent("2027");
    expect(dead).toHaveTextContent("Cut Guy");
    expect(dead).toHaveTextContent("$4.5M");
    expect(within(screen.getByRole("region", { name: "All contracts" })).getAllByRole("row")[1])
      .toHaveTextContent("$24.0M");
  });

  it("waits for the season to end before negotiating", () => {
    render(<ContractsView data={{ ...data, window_open: false,
      season: { ...data.season, phase: "regular_season" } }} team={team} />);
    expect(screen.queryByRole("button", { name: /Negotiate/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Re-signing opens when the season is over/)).toBeInTheDocument();
  });

  it("negotiates: a counter-offer, then a deal", async () => {
    mocked.reSign
      .mockResolvedValueOnce({ accepted: false, player: star,
        counter: { salary: 20_350_000, years: 5 },
        message: "Star Receiver wants at least $20.35M a year for 5 years." })
      .mockResolvedValueOnce({ accepted: true, counter: null, player: star,
        message: "Star Receiver signs for 5 years at $20.35M a year." });
    render(<ContractsView data={data} team={team} />);
    await userEvent.click(screen.getByRole("button", { name: "Negotiate with Star Receiver" }));
    const dialog = screen.getByRole("dialog", { name: "Re-sign Star Receiver" });

    await userEvent.selectOptions(within(dialog).getByLabelText("Years"), "5");
    await userEvent.click(within(dialog).getByRole("button", { name: "Offer $18.5M × 5" }));
    expect(mocked.reSign).toHaveBeenCalledWith(5, { salary: 18_500_000, years: 5 });
    expect(await within(dialog).findByRole("status")).toHaveTextContent("wants at least $20.35M");
    expect(within(dialog).getByLabelText("Salary per year ($M)")).toHaveValue(20.35);
    expect(router.refresh).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: /^Offer/ }));
    expect(mocked.reSign).toHaveBeenLastCalledWith(5, { salary: 20_350_000, years: 5 });
    expect(await within(dialog).findByText(/signs for 5 years/)).toBeInTheDocument();
    expect(router.refresh).toHaveBeenCalled();
  });
});
