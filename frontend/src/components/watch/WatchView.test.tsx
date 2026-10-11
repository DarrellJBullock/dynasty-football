import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PlaySceneProps } from "@/components/field/playback/PlayScene";
import { makePlay, makePlayback, pid, team } from "@/test/fixtures";
import { WatchView } from "./WatchView";

// The WebGL scene can't run in jsdom: stand in for it and keep its props, so tests can
// drive the playhead the way the real scene does every frame.
const scene = vi.hoisted(() => ({ props: null as PlaySceneProps | null }));
vi.mock("next/dynamic", () => ({
  default: () => function Scene(props: PlaySceneProps) {
    scene.props = props;
    return <div data-testid="scene" />;
  },
}));

const H = team.id;
const playback = makePlayback([
  makePlay({ text: "Nash runs for 6 yards.", result: { type: "run", yards: 6 }, score: { home: 0, away: 0 },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
             { t: "rush", player: pid(H, "RB"), yards: 6 }, { t: "tackle", by: [pid(2, "MLB")] }] }),
  makePlay({ down: 2, distance: 4, ball_on: 36, text: "Quarles pass complete to Wolfe for 64 yards. TOUCHDOWN.",
    result: { type: "pass", yards: 64, touchdown: true }, score: { home: 6, away: 0 },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "deep" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR"), result: "complete", air: 40, yards: 64 }] }),
  makePlay({ quarter: 2, clock: "9:12", down: 3, distance: 8, ball_on: 72, approximate: true,
    text: "Quarles sacked for a loss of 5.", result: { type: "sack", yards: -5 }, score: { home: 6, away: 0 },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "sack", qb: pid(H, "QB"), by: pid(2, "DE"), yards: -5 }] }),
]);

/** What the scene does each frame: report the playhead (advancing it while playing). */
function tick(time: number) {
  const { clock, timeline, onTick } = scene.props!;
  act(() => {
    clock.seek(Math.min(time, timeline.duration));
    const ended = clock.playing && time >= timeline.duration;
    if (ended) clock.setPlaying(false);
    onTick(clock.time, ended);
  });
}

beforeEach(() => {
  scene.props = null;
  window.history.replaceState(null, "", "/games/7/watch");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("WatchView", () => {
  it("opens on the requested play with its situation and text", () => {
    render(<WatchView playback={playback} initialPlay={2} />);
    expect(screen.getByTestId("play-text")).toHaveTextContent("64 yards. TOUCHDOWN.");
    expect(screen.getByText(/Play 2 of 3 · HFD 2nd & 4 at HFD 36/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Score" })).toHaveTextContent("ABQ 0HFD 0Q1 15:00");
    const current = within(screen.getByRole("complementary", { name: "Plays" }))
      .getAllByRole("button").find((b) => b.getAttribute("aria-current") === "true");
    expect(current).toHaveTextContent("Quarles pass complete");
    expect(scene.props!.timeline.players).toHaveLength(22);
    expect(scene.props!.clock.playing).toBe(true);
  });

  it("steps between plays and keeps the URL in step", async () => {
    const user = userEvent.setup();
    render(<WatchView playback={playback} />);
    expect(screen.getByRole("button", { name: "‹ Previous play" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next play ›" }));
    expect(screen.getByTestId("play-text")).toHaveTextContent("TOUCHDOWN");
    expect(window.location.search).toBe("?play=2");
    await user.click(screen.getByRole("button", { name: /sacked/ }));
    expect(screen.getByText(/Approximate lineup/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next play ›" })).toBeDisabled();
    expect(screen.getByRole("group", { name: "Score" })).toHaveTextContent("Q2 9:12");
    await user.click(screen.getByRole("button", { name: "‹ Previous play" }));
    expect(window.location.search).toBe("?play=2");
    expect(scene.props!.clock.time).toBe(0);
  });

  it("plays, pauses, scrubs and replays", async () => {
    const user = userEvent.setup();
    render(<WatchView playback={playback} initialPlay={2} />);
    const { timeline } = scene.props!;
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(scene.props!.clock.playing).toBe(false);

    // Scrubbing pauses and shows what's happening at that moment.
    const thrown = timeline.moments.find((m) => m.kind === "throw")!;
    fireEvent.change(screen.getByRole("slider", { name: "Play timeline" }), { target: { value: thrown.t + 0.05 } });
    expect(scene.props!.clock.time).toBeCloseTo(thrown.t + 0.05);
    expect(screen.getByRole("status")).toHaveTextContent(thrown.text);
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();

    // Played to the end: the score updates and the button offers a replay from the start.
    await user.click(screen.getByRole("button", { name: "Play" }));
    tick(timeline.duration);
    expect(screen.getByRole("group", { name: "Score" })).toHaveTextContent("HFD 6");
    expect(screen.getByRole("status")).toHaveTextContent("Whistle");
    expect(within(screen.getByRole("list", { name: "Moments" })).getByText("Touchdown, H. WR2!")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Replay" }));
    expect(scene.props!.clock.time).toBe(0);
    expect(scene.props!.clock.playing).toBe(true);
  });

  it("marks the play's moments on the scrubber", () => {
    render(<WatchView playback={playback} initialPlay={1} />);
    const moments = within(screen.getByRole("list", { name: "Moments" })).getAllByRole("listitem");
    expect(moments.map((m) => m.textContent)).toEqual(
      expect.arrayContaining(["Snap", "Handoff to H. RB1", "Tackled by A. MLB17", "Whistle"]));
  });

  it("sets the speed, camera and ball-following", async () => {
    const user = userEvent.setup();
    render(<WatchView playback={playback} />);
    await user.click(within(screen.getByRole("group", { name: "Speed" })).getByRole("button", { name: "2×" }));
    expect(scene.props!.clock.speed).toBe(2);
    const cameras = screen.getByRole("group", { name: "Camera" });
    expect(within(cameras).getByRole("button", { name: "Sideline" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(cameras).getByRole("button", { name: "All-22" }));
    expect(scene.props!.camera).toBe("all22");
    expect(within(cameras).queryByRole("button", { name: "Overview" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Follow ball" }));
    expect(scene.props!.follow).toBe(false);
  });

  it("plays the drive: on to the next play after each whistle", () => {
    vi.useFakeTimers();
    render(<WatchView playback={playback} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Play the drive" }));
    tick(scene.props!.timeline.duration);
    expect(screen.getByTestId("play-text")).toHaveTextContent("Nash runs");
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.getByTestId("play-text")).toHaveTextContent("TOUCHDOWN");
    expect(scene.props!.clock.playing).toBe(true);
  });

  it("takes the keyboard: space plays and pauses, arrows step", () => {
    render(<WatchView playback={playback} />);
    fireEvent.keyDown(window, { key: " " });
    expect(scene.props!.clock.playing).toBe(false);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByTestId("play-text")).toHaveTextContent("TOUCHDOWN");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByTestId("play-text")).toHaveTextContent("Nash runs");
  });

  it("says so when there's nothing to watch", () => {
    render(<WatchView playback={{ ...playback, plays: [] }} />);
    expect(screen.getByText("This game has no plays to watch.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Box score" })).toHaveAttribute("href", "/games/7");
  });
});
