import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { FreeAgencyOut } from "@/lib/types";
import { makePlayer, opponent, team } from "@/test/fixtures";
import { FreeAgencyView } from "./FreeAgencyView";

const router = { refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { makeOffer: vi.fn(), withdrawOffer: vi.fn(), signPlayer: vi.fn(),
    playFreeAgency: vi.fn() } };
});
const mocked = vi.mocked(api);

const ace = makePlayer({ id: 10, full_name: "Ace Corner", position: "CB", age: 26, overall: 84 });
const vet = makePlayer({ id: 11, full_name: "Vet Guard", position: "OG", age: 31, overall: 70 });

const market: FreeAgencyOut = {
  season: { id: 6, year: 2027, phase: "free_agency", current_week: 1, weeks: 17,
    regular_season_complete: false, next_round: null, champion: null, free_agency_day: 1 },
  open: true, day: 1, days: 5, demand: 1.15, open_spots: 6, cap_space: 30_000_000,
  players: [
    { player: ace, asking: { salary: 12_000_000, years: 4 }, offers: 3, my_offer: null, leading: null },
    { player: vet, asking: { salary: 2_000_000, years: 2 }, offers: 1,
      my_offer: { salary: 2_500_000, years: 2 }, leading: true },
  ],
  signings: [{ player: makePlayer({ id: 12, full_name: "Gone Early" }), team: opponent,
    salary: 9_000_000, years: 3, day: 1 }],
};

beforeEach(() => vi.clearAllMocks());

describe("FreeAgencyView", () => {
  it("shows the market: day, demand, players, my offers, signings", () => {
    render(<FreeAgencyView market={market} team={team} />);
    expect(screen.getByText(/Day 1 of 5\. Players want 115%/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Your situation" })).toHaveTextContent("Your offers1");
    const rows = within(screen.getByRole("region", { name: "Free agents" })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Ace Corner");
    expect(rows[1]).toHaveTextContent("$12.0M × 4");
    expect(rows[2]).toHaveTextContent("$2.5M × 2 · Leading");
    expect(screen.getByRole("region", { name: "Signings" })).toHaveTextContent("Gone Early");
    expect(screen.getByRole("button", { name: "Play free agency day 1" })).toBeInTheDocument();
  });

  it("filters by position", async () => {
    render(<FreeAgencyView market={market} team={team} />);
    await userEvent.selectOptions(screen.getByLabelText("Position"), "OG");
    const region = screen.getByRole("region", { name: "Free agents" });
    expect(within(region).queryByText("Ace Corner")).not.toBeInTheDocument();
    expect(within(region).getByText("Free agents (1)")).toBeInTheDocument();
  });

  it("makes an offer starting from today's demand", async () => {
    mocked.makeOffer.mockResolvedValue(undefined);
    render(<FreeAgencyView market={market} team={team} />);
    await userEvent.click(screen.getByRole("button", { name: "Make an offer to Ace Corner" }));
    const dialog = screen.getByRole("dialog", { name: "Offer Ace Corner" });
    expect(within(dialog).getByLabelText("Salary per year ($M)")).toHaveValue(13.8); // 115%
    await userEvent.click(within(dialog).getByRole("button", { name: "Offer $13.8M × 4" }));
    expect(mocked.makeOffer).toHaveBeenCalledWith(10, { salary: 13_800_000, years: 4 });
    expect(router.refresh).toHaveBeenCalled();
  });

  it("withdraws an offer", async () => {
    mocked.withdrawOffer.mockResolvedValue(undefined);
    render(<FreeAgencyView market={market} team={team} />);
    await userEvent.click(screen.getByRole("button", { name: "Withdraw offer to Vet Guard" }));
    expect(mocked.withdrawOffer).toHaveBeenCalledWith(11);
  });

  it("signs instantly outside free agency", async () => {
    mocked.signPlayer.mockResolvedValue(undefined as never);
    render(<FreeAgencyView market={{ ...market, open: false, day: null, demand: null,
      season: { ...market.season, phase: "regular_season" } }} team={team} />);
    expect(screen.queryByRole("button", { name: /Play free agency/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign Ace Corner" }));
    expect(mocked.signPlayer).toHaveBeenCalledWith(team.id, 10, 4);
  });
});
