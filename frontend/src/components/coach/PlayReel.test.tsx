import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { choreographGame } from "@/components/field/playback/choreograph";
import type { PlaySceneProps } from "@/components/field/playback/PlayScene";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { PlayReel } from "./PlayReel";

const scene = vi.hoisted(() => ({ props: null as PlaySceneProps | null }));
vi.mock("next/dynamic", () => ({
  default: () => function Scene(props: PlaySceneProps) {
    scene.props = props;
    return <div data-testid="scene" />;
  },
}));

// The Unity build: not installed unless a test says so.
const unity = vi.hoisted(() => ({ build: null as unknown }));
vi.mock("@/lib/unity", () => ({ unityBuild: () => Promise.resolve(unity.build) }));

const H = 1;
const playback = makePlayback([
  makePlay({ ball_on: 40, score: { home: 6, away: 0 }, text: "A 60-yard touchdown run.",
    result: { type: "run", yards: 60, touchdown: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "outside" }, { t: "rush", player: pid(H, "RB"), yards: 60 }] }),
  makePlay({ down: null, distance: null, ball_on: null, personnel: null, defense: null, score: { home: 7, away: 0 },
    text: "Extra point is good.", result: { type: "conversion" },
    events: [{ t: "extra_point", kicker: pid(H, "K"), good: true }] }),
]);
const reel = choreographGame(playback);

function endPlay() {
  const { clock, timeline, onTick } = scene.props!;
  act(() => {
    clock.seek(timeline.duration);
    clock.setPlaying(false);
    onTick(timeline.duration, true);
  });
}

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

describe("PlayReel instant replays", () => {
  it("replays a highlight in a reel of several plays before moving on", () => {
    render(<PlayReel playback={playback} reel={reel} />);
    endPlay();
    act(() => { vi.advanceTimersByTime(800); });
    expect(screen.getByRole("group", { name: "Instant replay" })).toBeInTheDocument();
    expect(scene.props!.cues).toEqual([{ t: 0, shot: "reverse" }]);
    expect(screen.getByTestId("reel-text")).toHaveTextContent("touchdown run");
    act(() => { scene.props!.onTick(scene.props!.timeline.duration - 0.2, false); }); // past its stretch
    expect(screen.queryByRole("group", { name: "Instant replay" })).not.toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(800); });
    expect(screen.getByTestId("reel-text")).toHaveTextContent("Extra point");
  });

  it("doesn't replay a single call's play", () => {
    render(<PlayReel playback={playback} reel={reel.slice(0, 1)} />);
    endPlay();
    act(() => { vi.advanceTimersByTime(2000); });
    expect(screen.queryByRole("group", { name: "Instant replay" })).not.toBeInTheDocument();
  });
});

describe("PlayReel's renderer", () => {
  afterEach(() => {
    unity.build = null;
    localStorage.clear();
  });

  it("draws in Unity when that's the choice, and falls back to Classic if Unity fails", async () => {
    unity.build = { loader: "Build/unity.loader.js" };
    localStorage.setItem("dynasty.renderer", "unity"); // (chosen on the Watch page)
    render(<PlayReel playback={playback} reel={reel} />);
    await act(async () => {});
    const renderer = screen.getByRole("group", { name: "Renderer" });
    expect(screen.getByRole("button", { name: "Unity" })).toHaveAttribute("aria-pressed", "true");
    expect(scene.props).toHaveProperty("onError");
    expect(renderer).toBeInTheDocument();

    act(() => (scene.props as unknown as { onError: (m: string) => void }).onError("Out of memory."));
    expect(screen.getByRole("alert")).toHaveTextContent("The Unity viewer stopped: Out of memory.");
    expect(screen.getByRole("button", { name: "Classic" })).toHaveAttribute("aria-pressed", "true");
    expect(scene.props).not.toHaveProperty("onError");
  });

  it("offers Unity only when it's installed", async () => {
    render(<PlayReel playback={playback} reel={reel} />);
    await act(async () => {});
    expect(screen.getByRole("button", { name: "Unity" })).toBeDisabled();
  });
});
