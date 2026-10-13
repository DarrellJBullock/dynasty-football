import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { TradeAssetOut, TradeCenter, TradeOffer } from "@/lib/types";
import { makePlayer, opponent, team } from "@/test/fixtures";
import { TradesView } from "./TradesView";

const router = { refresh: vi.fn(), push: vi.fn(), replace: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { evaluateTrade: vi.fn(), proposeTrade: vi.fn(), makeTradeOffer: vi.fn(),
    counterOffer: vi.fn(), acceptOffer: vi.fn(), rejectOffer: vi.fn(), withdrawTradeOffer: vi.fn(),
    vetoOffer: vi.fn(), approveOffer: vi.fn(), reverseTrade: vi.fn() } };
});
const mocked = vi.mocked(api);

function playerAsset(id: number, name: string, value: number): TradeAssetOut {
  return { kind: "player", id, label: name, value, player: makePlayer({ id, full_name: name }) };
}

const center: TradeCenter = {
  season: { id: 5, league_id: 1, year: 2026, phase: "regular_season", current_week: 4, weeks: 17,
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
  partner_manager: null, managed: [], offers: [], review_hours: 0,
};

/** The same desk, with the partner run by another member, Robin. */
const managedCenter: TradeCenter = { ...center, partner_manager: "Robin", managed: [opponent.id] };

function offer(overrides: Partial<TradeOffer> = {}): TradeOffer {
  return { id: 30, from_team: opponent, to_team: team, from_manager: "Robin", to_manager: "Sam",
    gives: [{ kind: "player", id: 3, label: "QB Their Star (88)" }],
    gets: [{ kind: "player", id: 2, label: "WR My Backup (61)" }],
    note: "Interested?", status: "pending", reason: null, direction: "incoming", parent_id: null,
    created_at: "2026-10-12T00:00:00Z", expires_at: "2026-10-15T00:00:00Z", review_ends_at: null,
    ...overrides };
}

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

  it("sends an offer, with a note, to a team another member runs", async () => {
    mocked.evaluateTrade.mockResolvedValue({ acceptable: true, balance: 0.4,
      message: "The Roadrunners' manager decides: send them an offer.", problems: [], value_in: 8,
      value_needed: 20 });
    mocked.makeTradeOffer.mockResolvedValue(offer({ direction: "outgoing" }));
    render(<TradesView center={managedCenter} team={team} leagueId={4} />);
    expect(screen.getByRole("option", { name: /Roadrunners \(a member's team\)/ })).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Trade My Backup"));
    await userEvent.click(screen.getByLabelText("Trade Their Backup"));
    await screen.findByText(/manager decides/);
    await userEvent.type(screen.getByLabelText("Note to Robin (optional)"), "Depth for depth?");
    await userEvent.click(screen.getByRole("button", { name: "Send offer" }));
    expect(mocked.makeTradeOffer).toHaveBeenCalledWith(4, { partner_id: opponent.id,
      send_players: [2], send_picks: [], receive_players: [4], receive_picks: [] }, "Depth for depth?");
    expect(await screen.findByRole("status", { name: "Trade result" })).toHaveTextContent("Offer sent to Robin.");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("answers an offer: accept, or reject", async () => {
    mocked.acceptOffer.mockResolvedValue(offer({ status: "accepted" }));
    mocked.rejectOffer.mockResolvedValue(offer({ id: 31, status: "rejected" }));
    render(<TradesView center={{ ...managedCenter, offers: [offer(), offer({ id: 31 })] }} team={team} leagueId={4} />);
    const offers = screen.getByRole("region", { name: "Trade offers" });
    const [first, second] = within(offers).getAllByRole("listitem");
    expect(first).toHaveTextContent(/You get\s*QB Their Star \(88\)/);
    expect(first).toHaveTextContent(/You give\s*WR My Backup \(61\)/);
    expect(first).toHaveTextContent("“Interested?”");
    await userEvent.click(within(first).getByRole("button", { name: "Accept" }));
    expect(mocked.acceptOffer).toHaveBeenCalledWith(30);
    expect(await within(offers).findByRole("status")).toHaveTextContent("done");
    await userEvent.click(within(second).getByRole("button", { name: "Reject" }));
    expect(mocked.rejectOffer).toHaveBeenCalledWith(31);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("counters an offer: the deal starts from it, sides swapped", async () => {
    mocked.evaluateTrade.mockResolvedValue({ acceptable: true, balance: 1, message: "decides",
      problems: [], value_in: 1, value_needed: 1 });
    mocked.counterOffer.mockResolvedValue(offer({ id: 32, direction: "outgoing", parent_id: 30 }));
    render(<TradesView center={{ ...managedCenter, offers: [offer()] }} team={team} leagueId={4}
      counterId={30} />);
    const deal = screen.getByRole("region", { name: "Deal" });
    expect(within(deal).getByRole("group", { name: "You give" })).toHaveTextContent("My Backup");
    expect(within(deal).getByRole("group", { name: "You get" })).toHaveTextContent("Their Star");
    await userEvent.click(screen.getByLabelText("Trade Their Star"));
    await userEvent.click(screen.getByLabelText("Trade Their Backup"));
    await userEvent.click(screen.getByRole("button", { name: "Send counter-offer" }));
    expect(mocked.counterOffer).toHaveBeenCalledWith(30, { partner_id: opponent.id,
      send_players: [2], send_picks: [], receive_players: [4], receive_picks: [] }, "");
    expect(router.replace).toHaveBeenCalledWith(`/trades?partner=${opponent.id}`);
  });

  it("withdraws your own offer, and lets a commissioner veto one in the window", async () => {
    mocked.withdrawTradeOffer.mockResolvedValue(offer({ direction: "outgoing", status: "withdrawn" }));
    mocked.vetoOffer.mockResolvedValue(offer({ id: 33, direction: "other", status: "vetoed" }));
    const mine = offer({ direction: "outgoing", from_team: team, to_team: opponent });
    const review = offer({ id: 33, direction: "other", status: "review",
      review_ends_at: "2026-10-13T12:00:00Z" });
    const { rerender } = render(<TradesView center={{ ...managedCenter, offers: [mine, review] }}
      team={team} leagueId={4} />);
    const offers = screen.getByRole("region", { name: "Trade offers" });
    const [own, waiting] = within(offers).getAllByRole("listitem");
    expect(within(waiting).queryByRole("button", { name: "Veto" })).toBeNull(); // (not a commissioner)
    await userEvent.click(within(own).getByRole("button", { name: "Withdraw" }));
    expect(mocked.withdrawTradeOffer).toHaveBeenCalledWith(30);
    rerender(<TradesView center={{ ...managedCenter, offers: [mine, review] }} team={team} leagueId={4}
      commissioner />);
    expect(waiting).toHaveTextContent("Accepted · in the veto window");
    await userEvent.click(within(waiting).getByRole("button", { name: "Veto" }));
    expect(mocked.vetoOffer).toHaveBeenCalledWith(33);
  });

  it("lets the commissioner reverse a trade from this season", async () => {
    const norfolk = { ...opponent, id: 3, full_name: "Norfolk Squall", nickname: "Squall", abbreviation: "NOR" };
    const trades = [
      { id: 21, team: norfolk, partner: opponent, season_phase: "regular_season", week: 3,
        sent: [{ kind: "player" as const, id: 8, label: "QB Ari Vance (80)" }],
        received: [{ kind: "pick" as const, id: 71, label: "2027 round 2" }], reversed: false, problem: null },
      { id: 20, team: norfolk, partner: opponent, season_phase: "regular_season", week: 2,
        sent: [{ kind: "player" as const, id: 9, label: "RB Bo Lane (70)" }], received: [],
        reversed: false, problem: "Bo Lane is no longer with the team he was traded to." },
    ];
    mocked.reverseTrade.mockResolvedValue({ ...trades[0], reversed: true, problem: "It's already been reversed." });
    render(<TradesView center={{ ...center, season_trades: trades,
      history: [{ ...center.history[0], reversed: true }] }} team={team} leagueId={4} commissioner />);
    expect(screen.getByRole("region", { name: "Trade history" })).toHaveTextContent("Reversed by the commissioner");
    const list = screen.getByRole("region", { name: "This season's trades" });
    expect(list).toHaveTextContent("Bo Lane is no longer with the team he was traded to.");
    await userEvent.click(within(list).getByRole("button", {
      name: "Reverse the trade between the Squall and the Roadrunners" }));
    await userEvent.click(within(list).getByRole("button", { name: "Confirm: reverse it" }));
    expect(mocked.reverseTrade).toHaveBeenCalledWith(21);
    expect(await within(list).findByRole("status")).toHaveTextContent("have everyone back");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("shows managers no season list", () => {
    render(<TradesView center={{ ...center, season_trades: [] }} team={team} leagueId={4} />);
    expect(screen.queryByRole("region", { name: "This season's trades" })).not.toBeInTheDocument();
  });
});
