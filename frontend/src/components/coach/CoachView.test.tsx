import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { CoachSituation, CoachState, Playbook, PlayOut } from "@/lib/types";
import { makePlay, makePlayback, opponent, team } from "@/test/fixtures";
import { CoachView } from "./CoachView";

// The WebGL scene can't run in jsdom.
vi.mock("next/dynamic", () => ({ default: () => function Scene() { return <div data-testid="scene" />; } }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { startCoaching: vi.fn(), coachCall: vi.fn(), coachAuto: vi.fn(), playback: vi.fn() } };
});
const mocked = vi.mocked(api);

const playbook: Playbook = {
  offense: [
    { key: "inside_zone", name: "Inside Zone", category: "run", formation: "Singleback", kind: "run",
      description: "Zone run.", direction: "inside", depth: null, play_action: false, targets: null },
    { key: "slants", name: "Slants", category: "quick", formation: "Shotgun", kind: "pass",
      description: "Quick slants.", direction: null, depth: "short", play_action: false, targets: [3, 3, 2, 1, 1] },
    { key: "smash", name: "Smash", category: "intermediate", formation: "Shotgun", kind: "pass",
      description: "Hitch and corner.", direction: null, depth: "medium", play_action: false, targets: [3, 2, 2, 1, 0] },
  ],
  defense: [
    { key: "cover2", name: "Cover 2", category: "zone", shell: "cover2", coverage: "zone", blitz: false,
      description: "Two deep.", package: null },
    { key: "cover3", name: "Cover 3", category: "zone", shell: "cover3", coverage: "zone", blitz: false,
      description: "Three deep.", package: null },
    { key: "cover0", name: "Cover 0 Blitz", category: "pressure", shell: "cover0", coverage: "man", blitz: true,
      description: "All out.", package: null },
  ],
};

const game = { id: 7, week: 3, home: team, away: opponent, home_score: null, away_score: null,
  status: "scheduled", overtime: false, stage: "regular" as const, round_name: null, neutral_site: false };
const season = { id: 1, year: 2026, phase: "regular_season", current_week: 3, weeks: 17,
  regular_season_complete: false, next_round: null, free_agency_day: null, champion: null };

function situation(overrides: Partial<CoachSituation> = {}): CoachSituation {
  return { role: "offense", quarter: 1, clock: "15:00", seconds: 900, clock_running: false,
    possession: "home", offense: "HFD", down: 1, distance: 10, ball_on: 30, spot: "HFD 30",
    score: { home: 0, away: 0 }, timeouts: { home: 3, away: 3 }, suggestion: "slants",
    suggestion_name: "Slants", suggested_package: null, ...overrides };
}

const play = (n: number, text: string, extra: Partial<PlayOut> = {}): PlayOut => ({
  n, quarter: 1, clock: "15:00", offense: "HFD", down: 1, distance: 10, spot: "HFD 30", type: "pass",
  text, home_score: 0, away_score: 0, scoring: false, ...extra });

function state(overrides: Partial<CoachState> = {}): CoachState {
  return { game, team, side: "home", status: "in_progress", autopilot: false, calls: 0,
    situation: situation(), plays: [play(1, "ABQ kicks off for a touchback.", { type: "kickoff", down: null })],
    new_plays: 1, season, ...overrides };
}

const playback = makePlayback([
  makePlay({ text: "ABQ kicks off for a touchback.", down: null, distance: null, ball_on: null, personnel: null,
    side: "away", offense: "ABQ", result: { type: "kickoff" },
    events: [{ t: "kickoff", kicker: 225, touchback: true, return: 0 }] }),
  makePlay({ text: "Quarles pass complete for 14 yards.", play_name: "Smash", defense_name: "Cover 1",
    result: { type: "pass", yards: 14, result: "complete" },
    events: [{ t: "dropback", qb: 100, depth: "medium" },
             { t: "pass", qb: 100, target: 102, result: "complete", air: 10, yards: 14 },
             { t: "tackle", by: [218] }] }),
]);

function renderView(initial: CoachState | null = state()) {
  return render(<CoachView game={game} playbook={playbook} initialState={initial}
    initialPlayback={initial ? { ...playback, plays: playback.plays.slice(0, 1) } : null} />);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.playback.mockResolvedValue(playback);
});

describe("CoachView", () => {
  it("offers to start, then puts you on the headset", async () => {
    const user = userEvent.setup();
    mocked.startCoaching.mockResolvedValue(state());
    renderView(null);
    await user.click(screen.getByRole("button", { name: "Start coaching" }));
    expect(mocked.startCoaching).toHaveBeenCalledWith(7);
    expect(await screen.findByRole("heading", { name: "Your offense" })).toBeInTheDocument();
    expect(screen.getByTestId("situation")).toHaveTextContent("HFD 1st & 10 at HFD 30");
  });

  it("opens the playbook on the AI's pick and calls the play you choose", async () => {
    const user = userEvent.setup();
    mocked.coachCall.mockResolvedValue(state({
      calls: 1, new_plays: 1, situation: situation({ down: 1, ball_on: 44, spot: "HFD 44", clock_running: true }),
      plays: [play(2, "Quarles pass complete for 14 yards.", { play_name: "Smash", defense_name: "Cover 1" }),
              ...state().plays] }));
    renderView();
    expect(screen.getByRole("tab", { name: "Quick" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Slants (AI pick)" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Intermediate" }));
    await user.click(screen.getByRole("button", { name: "Smash" }));
    expect(mocked.coachCall).toHaveBeenCalledWith(7, { play: "smash", timeout: false, package: null });
    expect(await screen.findByTestId("reel-text")).toHaveTextContent("pass complete for 14 yards");
    expect(screen.getByTestId("situation")).toHaveTextContent("at HFD 44");
    const log = screen.getByRole("complementary", { name: "Play-by-play" });
    expect(log).toHaveTextContent("Smash vs Cover 1");
  });

  it("calls the AI's suggestion, with a timeout while the clock runs", async () => {
    const user = userEvent.setup();
    mocked.coachCall.mockResolvedValue(state());
    const { unmount } = renderView();
    const timeout = screen.getByRole("checkbox", { name: /Call a timeout first/ });
    expect(timeout).toBeDisabled(); // the clock is stopped
    unmount();

    renderView(state({ situation: situation({ clock_running: true, timeouts: { home: 1, away: 3 } }) }));
    const running = screen.getByRole("checkbox", { name: /Call a timeout first \(1 left\)/ });
    await user.click(running);
    await user.click(screen.getByRole("button", { name: "Call it" }));
    expect(mocked.coachCall).toHaveBeenCalledWith(7, { play: "slants", package: null, timeout: true });
  });

  it("on defense, picks the personnel too", async () => {
    const user = userEvent.setup();
    mocked.coachCall.mockResolvedValue(state());
    renderView(state({ side: "away", situation: situation({ role: "defense", suggestion: "cover0",
      suggestion_name: "Cover 0 Blitz", suggested_package: "nickel" }) }));
    expect(screen.getByRole("heading", { name: "Your defense" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pressure" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("radio", { name: "Auto (nickel)" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "dime" }));
    await user.click(screen.getByRole("tab", { name: "Zone" }));
    await user.click(screen.getByRole("button", { name: "Cover 3" }));
    expect(mocked.coachCall).toHaveBeenCalledWith(7, { play: "cover3", timeout: false, package: "dime" });
  });

  it("makes the kicking decisions: the kickoff and the conversion", async () => {
    const user = userEvent.setup();
    mocked.coachCall.mockResolvedValue(state({ situation: situation({ role: "conversion",
      suggestion: "kick", suggestion_name: "Extra point", score: { home: 6, away: 7 } }) }));
    renderView(state({ plays: [], situation: situation({ role: "kickoff", suggestion: "normal",
      suggestion_name: "Kick it deep" }) }));
    expect(screen.getByRole("heading", { name: "Your kickoff" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument(); // no playbook
    expect(screen.queryByRole("checkbox", { name: /timeout/ })).not.toBeInTheDocument();
    const kickoff = screen.getByRole("list", { name: "Kickoff" });
    expect(within(kickoff).getByRole("button", { name: "Kick it deep (AI pick)" })).toBeInTheDocument();
    await user.click(within(kickoff).getByRole("button", { name: "Onside kick" }));
    expect(mocked.coachCall).toHaveBeenCalledWith(7, { play: "onside" });

    expect(await screen.findByRole("heading", { name: "After the touchdown" })).toBeInTheDocument();
    expect(screen.getByTestId("situation")).toHaveTextContent("Touchdown! Q1 15:00 · score 6–7");
    await user.click(screen.getByRole("button", { name: "Go for two" }));
    expect(mocked.coachCall).toHaveBeenLastCalledWith(7, { play: "two" });
  });

  it("hands the AI a play, the drive, or the rest of the game", async () => {
    const user = userEvent.setup();
    mocked.coachAuto.mockResolvedValue(state());
    renderView();
    const ai = screen.getByRole("group", { name: "Let the AI call" });
    await user.click(within(ai).getByRole("button", { name: "This play" }));
    expect(mocked.coachAuto).toHaveBeenLastCalledWith(7, "play");
    await user.click(within(ai).getByRole("button", { name: "This drive" }));
    expect(mocked.coachAuto).toHaveBeenLastCalledWith(7, "drive");

    mocked.coachAuto.mockResolvedValue(state({
      status: "final", situation: null, new_plays: 90,
      game: { ...game, status: "final", home_score: 27, away_score: 20 } }));
    await user.click(within(ai).getByRole("button", { name: "The rest of the game" }));
    expect(mocked.coachAuto).toHaveBeenCalledTimes(2); // asks first
    await user.click(screen.getByRole("button", { name: "Confirm: the AI finishes the game" }));
    expect(mocked.coachAuto).toHaveBeenLastCalledWith(7, "game");
    const final = await screen.findByRole("region", { name: "Final" });
    expect(final).toHaveTextContent("You won, 27–20");
    expect(within(final).getByRole("link", { name: "Box score" })).toHaveAttribute("href", "/games/7");
    expect(screen.getByTestId("coach-score-home")).toHaveTextContent("27");
  });

  it("shows why a call failed", async () => {
    const user = userEvent.setup();
    mocked.coachCall.mockRejectedValue(new Error("You have no timeouts left."));
    renderView();
    await user.click(screen.getByRole("button", { name: "Call it" }));
    expect(await within(screen.getByRole("region", { name: "Your call" })).findByRole("alert"))
      .toHaveTextContent("You have no timeouts left.");
  });

  it("can hide the 3D plays", async () => {
    const user = userEvent.setup();
    renderView();
    expect(screen.getByRole("region", { name: "Last play" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Show plays in 3D" }));
    expect(screen.queryByRole("region", { name: "Last play" })).not.toBeInTheDocument();
  });

  it("says when the game has already been played", () => {
    render(<CoachView game={{ ...game, status: "final", home_score: 10, away_score: 3 }} playbook={playbook}
      initialState={null} initialPlayback={null} />);
    expect(screen.queryByRole("button", { name: "Start coaching" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Box score" })).toHaveAttribute("href", "/games/7");
  });
});
