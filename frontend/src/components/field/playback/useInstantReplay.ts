"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PlayClock } from "./clock";
import type { ReplayPlan } from "./replay";

const REPLAY_PAUSE = 700; // ms after the play before the replay rolls

type Phase = "idle" | "replaying" | "done";

/**
 * Runs an instant replay once a play has ended: a beat later the playhead jumps back to
 * the plan's start and plays its stretch again at the plan's (slower) speed, then lands on
 * the end of the play. `settled` is true once there's nothing left to replay, so callers
 * hold auto-advance until then. Call `track` from the scene's per-frame tick; `cancel` when
 * the viewer takes over (scrubbing, another play).
 */
export function useInstantReplay({ clock, plan, enabled, ended, playKey, duration, onSeek }: {
  clock: PlayClock;
  plan: ReplayPlan | null;
  enabled: boolean;
  ended: boolean;
  playKey: unknown; // the play being shown: a new one starts fresh
  duration: number;
  onSeek: (time: number) => void; // the playhead moved (for the controls' display)
}) {
  const [state, setState] = useState<{ key: unknown; phase: Phase }>({ key: playKey, phase: "idle" });
  const phase = state.key === playKey ? state.phase : "idle";
  const live = useRef({ phase, plan, speed: 1 });
  useEffect(() => {
    live.current.phase = phase;
    live.current.plan = plan;
  }, [phase, plan]);

  const stop = useCallback((seekToEnd: boolean) => {
    if (live.current.phase !== "replaying") return;
    clock.setSpeed(live.current.speed);
    clock.setPlaying(false);
    live.current.phase = "done";
    if (seekToEnd) {
      clock.seek(duration);
      onSeek(duration);
    }
    setState({ key: playKey, phase: "done" });
  }, [clock, duration, onSeek, playKey]);

  // Roll the replay a beat after the play ends.
  useEffect(() => {
    if (!enabled || !plan || !ended || phase !== "idle") return;
    const timer = setTimeout(() => {
      live.current.speed = clock.speed;
      live.current.phase = "replaying";
      clock.seek(plan.from);
      clock.setSpeed(clock.speed * plan.speed);
      clock.setPlaying(true);
      onSeek(plan.from);
      setState({ key: playKey, phase: "replaying" });
    }, REPLAY_PAUSE);
    return () => clearTimeout(timer);
  }, [clock, enabled, ended, onSeek, phase, plan, playKey]);

  /** Per frame: end the replay when it reaches the end of its stretch. */
  const track = useCallback((time: number) => {
    const { phase: now, plan: current } = live.current;
    if (now === "replaying" && current && time >= current.to) stop(true);
  }, [stop]);

  return {
    replaying: phase === "replaying",
    settled: !enabled || !plan || phase === "done",
    track,
    skip: useCallback(() => stop(true), [stop]),
    cancel: useCallback(() => stop(false), [stop]),
  };
}
