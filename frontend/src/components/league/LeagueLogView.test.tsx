import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { LeagueLogEntry } from "@/lib/types";
import { LeagueLogView } from "./LeagueLogView";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { leagueLog: vi.fn(), rollBack: vi.fn() } };
});
const mocked = vi.mocked(api);

const entry = (id: number, overrides: Partial<LeagueLogEntry> = {}): LeagueLogEntry => ({
  id, created_at: "2026-10-13T18:00:00Z", actor: "Sam", action: "player",
  summary: `Edited Player ${id}`, team_id: 1, player_id: 100 + id, changes: [], ...overrides });

beforeEach(() => vi.clearAllMocks());

describe("LeagueLogView", () => {
  it("lists who changed what, with before and after", () => {
    render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [
      entry(3, { changes: [{ field: "speed", before: 80, after: 99 }] }),
      entry(2, { action: "contract", summary: "Changed Ari Vance's contract", player_id: 7,
        changes: [{ field: "salary", before: 1_000_000, after: 4_000_000 }] }),
      entry(1, { action: "settings", summary: "Changed the league settings", player_id: null }),
    ] }} />);
    const items = within(screen.getByRole("region", { name: "League log entries" })).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Sam");
    expect(within(items[0]).getByRole("link", { name: "Edited Player 3" })).toHaveAttribute("href", "/players/103");
    expect(within(items[0]).getByRole("row", { name: /Speed/ })).toHaveTextContent(/80.*99/);
    expect(within(items[1]).getByRole("row", { name: /Salary/ })).toHaveTextContent(/\$1\.0M.*\$4\.0M/);
    expect(within(items[2]).queryByRole("link")).not.toBeInTheDocument();
  });

  it("filters by kind and loads older entries", async () => {
    mocked.leagueLog.mockResolvedValueOnce({ more: true, entries: [entry(9, { action: "veto", summary: "Vetoed a trade" })] })
      .mockResolvedValueOnce({ more: false, entries: [entry(4, { action: "veto", summary: "Vetoed another" })] });
    render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [entry(10)] }} />);
    await userEvent.selectOptions(screen.getByLabelText("Show"), "Trade vetoed");
    expect(mocked.leagueLog).toHaveBeenCalledWith(1, { action: "veto", before: undefined });
    expect(await screen.findByText("Vetoed a trade")).toBeInTheDocument();
    expect(screen.queryByText("Edited Player 10")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Older entries" }));
    expect(mocked.leagueLog).toHaveBeenLastCalledWith(1, { action: "veto", before: 9 });
    expect(await screen.findByText("Vetoed another")).toBeInTheDocument();
    expect(screen.getByText("Vetoed a trade")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Older entries" })).not.toBeInTheDocument();
  });

  it("says when there's nothing yet", () => {
    render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [] }} />);
    expect(screen.getByText(/Nothing yet/)).toBeInTheDocument();
  });

  it("lets the commissioner roll back the last week, once", async () => {
    mocked.rollBack.mockResolvedValue({ label: "Week 5" });
    mocked.leagueLog.mockResolvedValue({ more: false, entries: [
      entry(11, { action: "rollback", summary: "Rolled back Week 5", player_id: null })] });
    render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [] }} rollback="Week 5" />);
    const panel = screen.getByRole("region", { name: "Roll back a week" });
    await userEvent.click(within(panel).getByRole("button", { name: "Roll back Week 5" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm: roll back Week 5" }));
    expect(mocked.rollBack).toHaveBeenCalledWith(1);
    expect(await within(panel).findByRole("status")).toHaveTextContent("Week 5 was rolled back");
    expect(within(panel).getByText(/Nothing to roll back/)).toBeInTheDocument();
    expect(await screen.findByText("Rolled back Week 5")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("shows a manager no rollback, and a commissioner when there's none", () => {
    const { unmount } = render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [] }} />);
    expect(screen.queryByRole("region", { name: "Roll back a week" })).not.toBeInTheDocument();
    unmount();
    render(<LeagueLogView leagueId={1} initial={{ more: false, entries: [] }} rollback={null} />);
    expect(screen.getByRole("region", { name: "Roll back a week" })).toHaveTextContent("Nothing to roll back");
  });
});
