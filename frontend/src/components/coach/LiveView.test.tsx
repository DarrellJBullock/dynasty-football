import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { CoachSituation, LiveState, Playbook, PlayOut } from "@/lib/types";
import { makePlay, makePlayback, opponent, team } from "@/test/fixtures";
import { POLL_MS } from "./CoachView";
import { LiveView } from "./LiveView";

// The WebGL scene can't run in jsdom.
vi.mock("next/dynamic", () => ({ default: () => function Scene() { return <div data-testid="scene" />; } }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { liveGame: vi.fn(), offerLive: vi.fn(), acceptLive: vi.fn(), declineLive: vi.fn(),
    liveCall: vi.fn(), liveAuto: vi.fn(), playback: vi.fn() } };
});
const mocked = vi.mocked(api);

const playbook: Playbook = {
  offense: [
    { key: "slants", name: "Slants", category: "quick", formation: "Shotgun", kind: "pass",
      description: "Quick slants.", direction: null, depth: "short", play_action: false, targets: [3, 3, 2, 1, 1] },
  ],
  defense: [
    { key: "cover2", name: "Cover 2", category: "zone", shell: "cover2", coverage: "zone", blitz: false,
      description: "Two deep.", package: null },
  ],
};

const game = { id: 7, week: 3, home: team, away: opponent, home_score: null, away_score: null,
  status: "scheduled", overtime: false, stage: "regular" as const, round_name: null, neutral_site: false };

const situation: CoachSituation = {
  role: "offense", quarter: 1, clock: "15:00", seconds: 900, clock_running: false,
  possession: "home", offense: "HFD", down: 1, distance: 10, ball_on: 30, spot: "HFD 30",
  score: { home: 0, away: 0 }, timeouts: { home: 3, away: 3 }, suggestion: "slants",
  suggestion_name: "Slants", suggested_package: null };

const play = (n: number, text: string, extra: Partial<PlayOut> = {}): PlayOut => ({
  n, quarter: 1, clock: "15:00", offense: "HFD", down: 1, distance: 10, spot: "HFD 30", type: "pass",
  text, home_score: 0, away_score: 0, scoring: false, ...extra });

function live(overrides: Partial<LiveState> = {}): LiveState {
  return { game, status: "in_progress", side: "home", team, proposed_by_you: false,
    managers: { home: "Sam", away: "Robin" }, clock_seconds: null, deadline: null, autopilot: false,
    situation, waiting_on: [], plays: [play(1, "ABQ kicks off for a touchback.", { type: "kickoff", down: null })],
    new_plays: 0, ...overrides };
}

const playback = makePlayback([
  makePlay({ text: "ABQ kicks off for a touchback.", down: null, distance: null, ball_on: null, personnel: null,
    side: "away", offense: "ABQ", result: { type: "kickoff" },
    events: [{ t: "kickoff", kicker: 225, touchback: true, return: 0 }] }),
]);

function renderView(initial: LiveState | null) {
  return render(<LiveView game={game} playbook={playbook} initialLive={initial}
    initialPlayback={initial ? playback : null} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.playback.mockResolvedValue(playback);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LiveView", () => {
  it("offers to play the game live, with a call clock", async () => {
    mocked.offerLive.mockResolvedValue(live({ status: "proposed", proposed_by_you: true, clock_seconds: 600,
      situation: null, plays: [] }));
    renderView(null);
    await userEvent.selectOptions(screen.getByLabelText("Call clock"), "10 minutes a call");
    await userEvent.click(screen.getByRole("button", { name: "Offer to play it live" }));
    expect(mocked.offerLive).toHaveBeenCalledWith(7, 600);
    expect(await screen.findByText(/Waiting for Robin to say yes/)).toBeInTheDocument();
    expect(screen.getByText(/10 minutes a call/)).toBeInTheDocument();
  });

  it("says yes to an offer and starts coaching", async () => {
    mocked.acceptLive.mockResolvedValue(live());
    renderView(live({ status: "proposed", situation: null, plays: [] }));
    expect(screen.getByText(/Robin wants to play this game live with you \(no clock\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Play it live" }));
    expect(await screen.findByRole("heading", { name: "Your offense" })).toBeInTheDocument();
    expect(screen.getByText(/^Live ·/)).toBeInTheDocument();
  });

  it("says no", async () => {
    mocked.declineLive.mockResolvedValue(live({ status: "declined", situation: null, plays: [] }));
    renderView(live({ status: "proposed", situation: null, plays: [] }));
    await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
    expect(await screen.findByText(/simulated from both game plans/)).toBeInTheDocument();
  });

  it("calls a play, waits blind on the other coach, then sees the snap", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mocked.liveCall.mockResolvedValue(live({ situation: null, waiting_on: ["ABQ"] }));
    renderView(live());
    await user.click(screen.getByRole("button", { name: "Slants (AI pick)" }));
    expect(mocked.liveCall).toHaveBeenCalledWith(7, { play: "slants", timeout: false, package: null });
    expect(await screen.findByRole("heading", { name: "Waiting on ABQ" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Scoreboard" })).toHaveTextContent("Live");

    mocked.liveGame.mockResolvedValue(live({
      plays: [play(1, "ABQ kicks off for a touchback.", { type: "kickoff", down: null }),
              play(2, "Quarles pass complete for 14 yards.")],
      situation: { ...situation, down: 1, spot: "HFD 44" } }));
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_MS); });
    expect(mocked.liveGame).toHaveBeenCalledWith(7);
    expect(screen.getByRole("heading", { name: "Your offense" })).toBeInTheDocument();
    expect(screen.getByText("Quarles pass complete for 14 yards.")).toBeInTheDocument();
  });

  it("shows the deadline when there's a call clock", () => {
    renderView(live({ situation: null, waiting_on: ["ABQ"], clock_seconds: 120,
      deadline: "2026-10-13T20:00:00Z" }));
    expect(screen.getByText(/the AI calls it from their game plan/)).toBeInTheDocument();
  });

  it("lets other members watch", () => {
    renderView(live({ side: null, team: null, situation: null }));
    expect(screen.getByText(/Robin and Sam are playing this game live/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Watch it" })).toHaveAttribute("href", "/games/7/watch");
  });
});
