import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { TradeAssetOut, TradeCenter } from "@/lib/types";
import { makePlayer, opponent, team } from "@/test/fixtures";
import { TradesView } from "./TradesView";

const router = { refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { evaluateTrade: vi.fn(), proposeTrade: vi.fn() } };
});
const mocked = vi.mocked(api);

function playerAsset(id: number, name: string, value: number): TradeAssetOut {
  return { kind: "player", id, label: name, value, player: makePlayer({ id, full_name: name }) };
}

const center: TradeCenter = {
  season: { id: 5, year: 2026, phase: "regular_season", current_week: 4, weeks: 17,
    regular_season_complete: false, next_round: null, champion: null },
  closed_reason: null, deadline_week: 10, draft_year: 2027,
  partners: [opponent, { ...opponent, id: 3, full_name: "Norfolk Squall", nickname: "Squall" }],
  partner: opponent,
  mine: { players: [playerAsset(1, "My Star", 120), playerAsset(2, "My Backup", 8)],
    picks: [{ kind: "pick", id: 50, label: "2027 round 1", value: 60, round: 1, year: 2027,
      projected_number: 14 }] },
  theirs: { players: [playerAsset(3, "Their Star", 110), playerAsset(4, "Their Backup", 6)],
    picks: [] },
  history: [{ id: 9, partner: opponent, season_phase: "preseason", week: 1,
    sent: [{ kind: "player", id: 7, label: "WR Old Friend (74)" }],
    received: [{ kind: "pick", id: 70, label: "2027 round 3" }] }],
};

beforeEach(() => vi.clearAllMocks());

describe("TradesView", () => {
  it("builds a deal and shows the other team's reaction", async () => {
    mocked.evaluateTrade.mockResolvedValue({ acceptable: false, balance: 0.6,
      message: "The Roadrunners want more: about 40 more trade value.", problems: [],
      value_in: 60, value_needed: 100 });
    render(<TradesView center={center} team={team} leagueId={4} />);
    expect(screen.getByRole("region", { name: "Trade history" })).toHaveTextContent(
      /sent WR Old Friend \(74\)\s*for\s*2027 round 3/);

    await userEvent.click(screen.getByLabelText("Trade My Backup"));
    await userEvent.click(screen.getByLabelText("Trade Their Star"));
    const deal = screen.getByRole("region", { name: "Deal" });
    expect(within(deal).getByRole("group", { name: "You give" })).toHaveTextContent("My Backup");
    expect(within(deal).getByRole("group", { name: "You get" })).toHaveTextContent("Their Star");
    await waitFor(() => expect(mocked.evaluateTrade).toHaveBeenLastCalledWith(4, {
      partner_id: opponent.id, send_players: [2], send_picks: [],
      receive_players: [3], receive_picks: [] }));
    expect(await screen.findByRole("status", { name: "Their answer" })).toHaveTextContent("want more");
    expect(screen.getByRole("meter", { name: "Trade meter" })).toHaveAttribute("aria-valuenow", "0.6");
  });

  it("proposes an acceptable trade", async () => {
    mocked.evaluateTrade.mockResolvedValue({ acceptable: true, balance: 1.3,
      message: "The Roadrunners would accept this trade.", problems: [], value_in: 130,
      value_needed: 100 });
    mocked.proposeTrade.mockResolvedValue({ accepted: true, evaluation: {} as never,
      trade: { ...center.history[0], id: 10 } });
    render(<TradesView center={center} team={team} leagueId={4} />);
    await userEvent.click(screen.getByLabelText("Trade 2027 round 1"));
    await userEvent.click(screen.getByLabelText("Trade Their Backup"));
    await screen.findByText("The Roadrunners would accept this trade.");
    await userEvent.click(screen.getByRole("button", { name: "Propose trade" }));
    expect(mocked.proposeTrade).toHaveBeenCalledWith(4, { partner_id: opponent.id,
      send_players: [], send_picks: [50], receive_players: [4], receive_picks: [] });
    expect(await screen.findByRole("status", { name: "Trade result" })).toHaveTextContent("Trade done");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("switches partners and respects a closed window", async () => {
    render(<TradesView center={{ ...center, closed_reason: "The trade deadline (week 10) has passed." }}
      team={team} leagueId={4} />);
    expect(screen.getByText("The trade deadline (week 10) has passed.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Trade My Star"));
    expect(screen.getByRole("button", { name: "Propose trade" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Trade with"), "3");
    expect(router.push).toHaveBeenCalledWith("/trades?partner=3");
  });
});
