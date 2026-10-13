import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RefreshOnReturn, UnreadBadge } from "@/components/shell/UnreadBadge";
import { api, ApiError } from "@/lib/api";
import type { Notification, NotificationSettings } from "@/lib/types";
import { announceUnread, InboxView } from "./InboxView";

const router = { refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { markRead: vi.fn(), setNotificationEmail: vi.fn(), unreadCount: vi.fn() } };
});
const mocked = vi.mocked(api);

function note(id: number, overrides: Partial<Notification> = {}): Notification {
  return { id, kind: "game_result", title: `Note ${id}`, body: "Week 3: the box score.",
    link: `/games/${id}`, league: "Harbor League", created_at: "2026-10-12T20:00:00Z", read: false,
    ...overrides };
}

const settings: NotificationSettings = { kinds: [
  { kind: "trade_offer", label: "A trade offer for you", email: false },
  { kind: "game_result", label: "Your team's result", email: true },
] };

beforeEach(() => vi.clearAllMocks());

describe("InboxView", () => {
  it("lists notifications, unread first marked, and opening one marks it read", async () => {
    mocked.markRead.mockResolvedValue({ unread: 1 });
    const told = vi.fn();
    window.addEventListener("dynasty:unread", told);
    render(<InboxView initial={{ unread: 2, items: [note(2), note(1, { title: "Robin offers a trade", link: "/trades" })] }}
      settings={null} leagueId={null} leagueName={null} />);
    const list = screen.getByRole("list", { name: "Notifications" });
    const offer = within(list).getByRole("listitem", { name: "Unread: Robin offers a trade" });
    expect(within(offer).getByRole("link")).toHaveAttribute("href", "/trades");
    expect(offer).toHaveTextContent("Harbor League");
    await userEvent.click(within(offer).getByRole("link"));
    expect(mocked.markRead).toHaveBeenCalledWith([1]);
    expect(await within(list).findByRole("listitem", { name: "Robin offers a trade" })).toBeInTheDocument();
    expect(told).toHaveBeenCalled(); // (the sidebar's badge hears the new count)
    window.removeEventListener("dynasty:unread", told);
  });

  it("marks everything read", async () => {
    mocked.markRead.mockResolvedValue({ unread: 0 });
    render(<InboxView initial={{ unread: 2, items: [note(2), note(1)] }} settings={null}
      leagueId={null} leagueName={null} />);
    expect(screen.getByRole("region", { name: "2 unread" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(mocked.markRead).toHaveBeenCalledWith(undefined);
    expect(await screen.findByRole("region", { name: "All caught up" })).toBeInTheDocument();
    expect(screen.queryByRole("listitem", { name: /^Unread/ })).toBeNull();
  });

  it("says when there's nothing yet", () => {
    render(<InboxView initial={{ unread: 0, items: [] }} settings={null} leagueId={null} leagueName={null} />);
    expect(screen.getByText(/Nothing yet/)).toBeInTheDocument();
  });

  it("chooses which kinds also come by email, and shows a refusal", async () => {
    mocked.setNotificationEmail
      .mockResolvedValueOnce({ kinds: settings.kinds.map((k) => ({ ...k, email: true })) })
      .mockRejectedValueOnce(new ApiError(422, "Unknown notifications: x."));
    render(<InboxView initial={{ unread: 0, items: [] }} settings={settings} leagueId={4}
      leagueName="Harbor League" />);
    const panel = screen.getByRole("region", { name: "Email me · Harbor League" });
    const offers = within(panel).getByRole("checkbox", { name: "A trade offer for you" });
    expect(offers).not.toBeChecked();
    expect(within(panel).getByRole("checkbox", { name: "Your team's result" })).toBeChecked();
    await userEvent.click(offers);
    expect(mocked.setNotificationEmail).toHaveBeenCalledWith(4, ["trade_offer", "game_result"]);
    expect(await within(panel).findByRole("status")).toHaveTextContent("Saved.");
    expect(offers).toBeChecked();
    await userEvent.click(offers);
    expect(await within(panel).findByRole("alert")).toHaveTextContent("Unknown notifications");
  });
});

describe("UnreadBadge", () => {
  afterEach(() => vi.useRealTimers());

  it("shows the count, polls it, and hears the inbox", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocked.unreadCount.mockResolvedValueOnce({ unread: 3 }).mockResolvedValue({ unread: 120 });
    render(<UnreadBadge pathname="/" />);
    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getByText("unread")).toHaveClass("sr-only");
    await act(async () => { vi.advanceTimersByTime(30_000); });
    expect(await screen.findByText("99+")).toBeInTheDocument();
    act(() => announceUnread(0));
    expect(screen.queryByText("99+")).toBeNull();
  });
});

describe("RefreshOnReturn", () => {
  it("refreshes the page's data when you come back to the tab", () => {
    render(<RefreshOnReturn />);
    const visibility = vi.spyOn(document, "visibilityState", "get");
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(router.refresh).not.toHaveBeenCalled();
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(router.refresh).toHaveBeenCalledTimes(1);
    visibility.mockRestore();
  });
});
