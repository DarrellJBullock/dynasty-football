import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { InvitePreview, Member, Members, TeamSummary, Turn } from "@/lib/types";
import { team } from "@/test/fixtures";
import { JoinLeague } from "./JoinLeague";
import { localToUtcMinutes, utcMinutesToLocal } from "./LeagueSettingsPanel";
import { shareUrl } from "./SharingPanel";
import { inviteUrl, MembersView } from "./MembersView";

const search = { value: "" };
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search.value) }));
vi.mock("@/lib/navigation", () => ({ hardNavigate: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { members: vi.fn(), createInvite: vi.fn(), revokeInvite: vi.fn(),
    setMemberRole: vi.fn(), removeMember: vi.fn(), previewInvite: vi.fn(), joinLeague: vi.fn(),
    turn: vi.fn(), updateLeagueSettings: vi.fn(), shareLeague: vi.fn(), unshareLeague: vi.fn() } };
});
const mocked = vi.mocked(api);

const rival: TeamSummary = { ...team, id: 2, city: "Salem", nickname: "Comets", full_name: "Salem Comets",
  abbreviation: "SAL" };
const open: TeamSummary = { ...team, id: 3, city: "Dover", nickname: "Owls", full_name: "Dover Owls",
  abbreviation: "DOV" };
const you: Member = { id: 1, display_name: "Coach Sam", role: "commissioner", team, is_you: true,
  joined_at: "2026-10-01T00:00:00Z" };
const friend: Member = { id: 2, display_name: "Robin", role: "manager", team: rival, is_you: false,
  joined_at: "2026-10-02T00:00:00Z" };
const league = { id: 1, name: "Harbor League", abbreviation: "HBL", salary_cap: 255_000_000, players: "men" as const };
const members: Members = { league, you, members: [you, friend], invites: [], open_teams: [open],
  shared_at: null };

const turn: Turn = { step: "Week 3", step_key: "1:week:3", managers: [], all_ready: false,
  can_advance: true, draft_clock_minutes: 1440, advance_minute_utc: null, next_advance_at: null,
  pick_clock_ends_at: null, trade_review_hours: 0 };

beforeEach(() => {
  vi.clearAllMocks();
  search.value = "";
  mocked.turn.mockResolvedValue(turn);
});

describe("MembersView", () => {
  it("lists who runs which team, and the teams the AI runs", () => {
    render(<MembersView initial={members} />);
    const robin = screen.getByRole("listitem", { name: "Robin" });
    expect(robin).toHaveTextContent("Manager · Salem Comets");
    expect(screen.getByRole("listitem", { name: "Coach Sam" })).toHaveTextContent("(you)");
    expect(screen.getByRole("region", { name: "Open teams" })).toHaveTextContent("Dover Owls");
  });

  it("makes an invite link to share, shown once, and revokes it", async () => {
    const invite = { id: 9, created_at: "2026-10-12T00:00:00Z", expires_at: "2026-10-19T00:00:00Z", uses: 0 };
    mocked.createInvite.mockResolvedValue({ ...invite, token: "abc123" });
    mocked.members.mockResolvedValueOnce({ ...members, invites: [invite] }).mockResolvedValueOnce(members);
    render(<MembersView initial={members} />);
    await userEvent.click(screen.getByRole("button", { name: "New invite link" }));
    expect(await screen.findByLabelText("Invite link (shown once)")).toHaveValue(
      inviteUrl(window.location.origin, "abc123"));
    const links = screen.getByRole("list", { name: "Open invite links" });
    expect(links).toHaveTextContent("used 0 times");
    await userEvent.click(within(links).getByRole("button", { name: "Revoke" }));
    expect(mocked.revokeInvite).toHaveBeenCalledWith(1, 9);
    await waitFor(() => expect(screen.queryByRole("list", { name: "Open invite links" })).toBeNull());
  });

  it("lets a commissioner change roles and remove a manager, after confirming", async () => {
    mocked.setMemberRole.mockResolvedValue({ ...members, members: [you, { ...friend, role: "commissioner" }] });
    mocked.members.mockResolvedValue({ ...members, members: [you] });
    render(<MembersView initial={members} />);
    const robin = screen.getByRole("listitem", { name: "Robin" });
    await userEvent.click(within(robin).getByRole("button", { name: "Make commissioner" }));
    expect(mocked.setMemberRole).toHaveBeenCalledWith(1, 2, "commissioner");
    expect(await within(robin).findByText(/Commissioner · Salem Comets/)).toBeInTheDocument();
    await userEvent.click(within(robin).getByRole("button", { name: "Remove…" }));
    expect(robin).toHaveTextContent("Comets go back to the AI.");
    await userEvent.click(within(robin).getByRole("button", { name: "Remove Robin" }));
    expect(mocked.removeMember).toHaveBeenCalledWith(1, 2);
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Robin" })).toBeNull());
  });

  it("gives a manager only the way out, and leaving goes to My Leagues", async () => {
    const asManager: Members = { ...members, you: { ...friend, is_you: true },
      members: [{ ...you, is_you: false }, { ...friend, is_you: true }] };
    render(<MembersView initial={asManager} />);
    expect(screen.queryByRole("button", { name: "New invite link" })).toBeNull();
    expect(within(screen.getByRole("listitem", { name: "Coach Sam" })).queryAllByRole("button")).toHaveLength(0);
    const me = screen.getByRole("listitem", { name: "Robin" });
    await userEvent.click(within(me).getByRole("button", { name: "Leave league…" }));
    await userEvent.click(within(me).getByRole("button", { name: "Leave" }));
    expect(mocked.removeMember).toHaveBeenCalledWith(1, 2);
    await waitFor(() => expect(hardNavigate).toHaveBeenCalledWith("/leagues"));
  });

  it("shows why a change was refused", async () => {
    mocked.removeMember.mockRejectedValue(new ApiError(409, "Make someone else a commissioner first."));
    render(<MembersView initial={members} />);
    const me = screen.getByRole("listitem", { name: "Coach Sam" });
    await userEvent.click(within(me).getByRole("button", { name: "Leave league…" }));
    await userEvent.click(within(me).getByRole("button", { name: "Leave" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Make someone else a commissioner first.");
  });
});

describe("JoinLeague", () => {
  const preview: InvitePreview = { league, commissioner: "Coach Sam", member_count: 2,
    open_teams: [open, { ...open, id: 4, full_name: "Bay Gulls", abbreviation: "BAY" }],
    already_member: false, your_team: null };

  it("shows the league, picks an open team, and joins", async () => {
    search.value = "token=abc123";
    mocked.previewInvite.mockResolvedValue(preview);
    mocked.joinLeague.mockResolvedValue({} as never);
    render(<JoinLeague />);
    expect(await screen.findByRole("heading", { name: "Join Harbor League" })).toBeInTheDocument();
    expect(mocked.previewInvite).toHaveBeenCalledWith("abc123");
    expect(screen.getByText(/Coach Sam is the commissioner · 2 members/)).toBeInTheDocument();
    const join = screen.getByRole("button", { name: "Join the league" });
    expect(join).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Bay Gulls/ }));
    await userEvent.click(join);
    expect(mocked.joinLeague).toHaveBeenCalledWith("abc123", 4);
    await waitFor(() => expect(hardNavigate).toHaveBeenCalledWith("/"));
  });

  it("explains a link that doesn't work any more", async () => {
    search.value = "token=old";
    mocked.previewInvite.mockRejectedValue(
      new ApiError(404, "This invite link isn't valid any more. Ask for a new one."));
    render(<JoinLeague />);
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't valid any more");
  });

  it("points a member who already runs a team back to their leagues", async () => {
    search.value = "token=abc123";
    mocked.previewInvite.mockResolvedValue({ ...preview, already_member: true, your_team: rival });
    render(<JoinLeague />);
    expect(await screen.findByText(/You already run the Salem Comets here/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Join the league" })).toBeNull();
  });
});

describe("LeagueSettingsPanel (on the Members page, for a commissioner)", () => {
  it("sets the draft clock and a daily advance, and turns it off", async () => {
    const offset = new Date().getTimezoneOffset();
    mocked.updateLeagueSettings
      .mockResolvedValueOnce({ ...turn, draft_clock_minutes: 60 })
      .mockResolvedValueOnce({ ...turn, draft_clock_minutes: 60, advance_minute_utc: localToUtcMinutes("20:30", offset),
        next_advance_at: "2026-10-13T00:30:00Z" })
      .mockResolvedValueOnce({ ...turn, draft_clock_minutes: 60 });
    render(<MembersView initial={members} />);
    const settings = await screen.findByRole("region", { name: "League settings" });
    await userEvent.selectOptions(within(settings).getByLabelText("Draft clock"), "1 hour");
    expect(mocked.updateLeagueSettings).toHaveBeenCalledWith(1, { draft_clock_minutes: 60 });
    expect(await within(settings).findByRole("status")).toHaveTextContent("Draft clock saved.");
    const time = within(settings).getByLabelText("Advance every day at (your time)");
    await userEvent.clear(time);
    await userEvent.type(time, "20:30");
    await userEvent.click(within(settings).getByRole("button", { name: "Advance daily" }));
    expect(mocked.updateLeagueSettings).toHaveBeenLastCalledWith(
      1, { advance_minute_utc: localToUtcMinutes("20:30", offset) });
    expect(await within(settings).findByText(/On: the league plays the next step/)).toBeInTheDocument();
    await userEvent.click(within(settings).getByRole("button", { name: "Turn off" }));
    expect(mocked.updateLeagueSettings).toHaveBeenLastCalledWith(1, { advance_minute_utc: null });
  });

  it("sets the trade veto window", async () => {
    mocked.updateLeagueSettings.mockResolvedValue({ ...turn, trade_review_hours: 24 });
    render(<MembersView initial={members} />);
    const settings = await screen.findByRole("region", { name: "League settings" });
    await userEvent.selectOptions(within(settings).getByLabelText("Trade veto window"), "24 hours");
    expect(mocked.updateLeagueSettings).toHaveBeenCalledWith(1, { trade_review_hours: 24 });
    expect(await within(settings).findByRole("status")).toHaveTextContent("Veto window saved.");
  });

  it("isn't there for a manager", () => {
    render(<MembersView initial={{ ...members, you: { ...friend, is_you: true } }} />);
    expect(screen.queryByRole("region", { name: "League settings" })).toBeNull();
  });

  it("converts the time of day both ways, across midnight", () => {
    expect(localToUtcMinutes("21:00", 300)).toBe(2 * 60); // UTC-5: 9 pm is 02:00 UTC
    expect(utcMinutesToLocal(2 * 60, 300)).toBe("21:00");
    expect(localToUtcMinutes("00:30", -120)).toBe(22 * 60 + 30); // UTC+2
    expect(utcMinutesToLocal(22 * 60 + 30, -120)).toBe("00:30");
  });
});

describe("SharingPanel (on the Members page)", () => {
  it("lets a commissioner share a read-only link, shown once, and stop sharing", async () => {
    mocked.shareLeague.mockResolvedValue({ token: "pub-123", shared_at: "2026-10-13T12:00:00Z" });
    mocked.unshareLeague.mockResolvedValue(undefined);
    render(<MembersView initial={members} />);
    const panel = screen.getByRole("region", { name: "Share and export" });
    expect(panel).toHaveTextContent("Not shared.");
    await userEvent.click(within(panel).getByRole("button", { name: "Share a read-only link" }));
    expect(mocked.shareLeague).toHaveBeenCalledWith(1);
    expect(await within(panel).findByLabelText("Public link (shown once)")).toHaveValue(
      shareUrl(window.location.origin, "pub-123"));
    expect(panel).toHaveTextContent("Shared since Oct 13");
    await userEvent.click(within(panel).getByRole("button", { name: "Stop sharing" }));
    expect(mocked.unshareLeague).toHaveBeenCalledWith(1);
    expect(await within(panel).findByText(/Not shared/)).toBeInTheDocument();
    expect(within(panel).queryByLabelText("Public link (shown once)")).toBeNull();
  });

  it("gives every member the download, and only a commissioner the link", () => {
    render(<MembersView initial={{ ...members, you: { ...friend, is_you: true }, shared_at: "2026-10-13T00:00:00Z" }} />);
    const panel = screen.getByRole("region", { name: "Share and export" });
    expect(within(panel).getByRole("link", { name: "Download the league (JSON)" }))
      .toHaveAttribute("href", "/api/leagues/1/export");
    expect(within(panel).queryByRole("button")).toBeNull();
  });
});
