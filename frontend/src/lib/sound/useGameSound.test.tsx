import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SoundControls } from "@/components/sound/SoundControls";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import { makePlay } from "@/test/fixtures";
import { DEFAULT_SOUND, resetSoundEngine, SOUND_KEY, useGameSound } from "./useGameSound";

// The engine makes sound with Web Audio, which jsdom doesn't have: stand in for it.
const fake = vi.hoisted(() => ({
  engine: {
    state: "running", play: vi.fn(), resume: vi.fn(() => Promise.resolve()), suspend: vi.fn(() => Promise.resolve()),
    setMix: vi.fn(), setCrowdLevel: vi.fn(),
  },
}));
vi.mock("./engine", () => ({ SoundEngine: { create: () => fake.engine } }));

const timeline = {
  duration: 4, direction: 1, los: 40, firstDownLine: 50, players: [], ball: [], flag: null,
  moments: [{ t: 1, kind: "snap", text: "Snap" }, { t: 2.5, kind: "tackle", text: "Tackle" },
            { t: 3, kind: "whistle", text: "Whistle" }],
} as unknown as PlayTimeline;
const game = { neutral_site: false, stage: "regular" as const };
const run = makePlay({ result: { type: "run", yards: 45 }, quarter: 4, score: { home: 14, away: 10 } });

beforeEach(() => {
  vi.clearAllMocks();
  resetSoundEngine();
  localStorage.clear();
});
afterEach(() => localStorage.clear());

function sound(replaying = false) {
  return renderHook(({ r }) => useGameSound({ game, play: run, timeline, replaying: r }),
                    { initialProps: { r: replaying } });
}
const played = () => fake.engine.play.mock.calls.map(([cue]) => cue.sound);

describe("a viewer's sound", () => {
  it("is off until the visitor turns it on, and that's remembered", () => {
    const { result } = sound();
    expect(result.current.settings).toEqual(DEFAULT_SOUND);
    act(() => result.current.onTime(1.1));
    expect(fake.engine.play).not.toHaveBeenCalled();

    act(() => result.current.update({ on: true, volume: 0.4 }));
    expect(fake.engine.resume).toHaveBeenCalled(); // (started by the click itself)
    expect(JSON.parse(localStorage.getItem(SOUND_KEY)!)).toMatchObject({ on: true, volume: 0.4 });
    expect(fake.engine.setMix).toHaveBeenLastCalledWith({ volume: 0.4, effects: true, crowd: true });
    // The crowd for the situation: a close game in the fourth quarter.
    expect(fake.engine.setCrowdLevel).toHaveBeenLastCalledWith(0.55);

    const again = sound();
    expect(again.result.current.settings.on).toBe(true);
  });

  it("plays each cue as the playhead passes it, and nothing it jumped over", () => {
    localStorage.setItem(SOUND_KEY, JSON.stringify({ on: true }));
    const { result } = sound();
    act(() => { for (let t = 0; t <= 1.2; t += 0.1) result.current.onTime(t); });
    // (A 45-yard run: the crowd starts to rise at the snap.)
    expect(played()).toEqual(["cadence", "snap", "swell"]);
    act(() => result.current.onTime(3.5)); // a scrub to the end
    expect(played()).toEqual(["cadence", "snap", "swell"]);
  });

  it("replays quieter, without the crowd's reaction", () => {
    localStorage.setItem(SOUND_KEY, JSON.stringify({ on: true }));
    const { result } = sound(true);
    act(() => { for (let t = 0; t <= 3.2; t += 0.1) result.current.onTime(t); });
    expect(played()).toContain("hit"); // the tackle still sounds
    expect(played()).not.toContain("cheer"); // (a 45-yard home run would get one live)
    expect(fake.engine.play.mock.calls.every(([, scale]) => scale === 0.5)).toBe(true);
  });

  it("quiets the crowd when the viewer goes away", () => {
    localStorage.setItem(SOUND_KEY, JSON.stringify({ on: true }));
    const { unmount } = sound();
    unmount();
    expect(fake.engine.setCrowdLevel).toHaveBeenLastCalledWith(0);
    expect(fake.engine.suspend).toHaveBeenCalled();
  });
});

describe("SoundControls", () => {
  it("turns sound on and shows the volume and the effects and crowd", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<SoundControls settings={DEFAULT_SOUND} onChange={onChange} />);
    expect(screen.queryByRole("slider", { name: "Volume" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sound off" }));
    expect(onChange).toHaveBeenCalledWith({ on: true });

    rerender(<SoundControls settings={{ ...DEFAULT_SOUND, on: true }} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Sound on" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("slider", { name: "Volume" })).toHaveAttribute("aria-valuetext", "70%");
    await userEvent.click(screen.getByRole("checkbox", { name: "Crowd" }));
    expect(onChange).toHaveBeenLastCalledWith({ crowd: false });
  });
});
