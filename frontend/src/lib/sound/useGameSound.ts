"use client";

/**
 * A viewer's sound (docs/design/sound.md): the visitor's settings (off until they turn it
 * on, remembered), the page's one engine, and the current play's cues, played as the
 * viewer's playhead passes them. Call `onTime` from the viewer's onTick.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import type { Game, PlaybackPlay } from "@/lib/types";
import { crowdLevel, dueCues, soundCues } from "./cues";
import { SoundEngine, type SoundMix } from "./engine";

export interface SoundSettings extends SoundMix { on: boolean }

export const SOUND_KEY = "dynasty.sound";
export const DEFAULT_SOUND: SoundSettings = { on: false, volume: 0.7, effects: true, crowd: true };

function loadSettings(): SoundSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(SOUND_KEY) ?? "null");
    return saved ? { ...DEFAULT_SOUND, ...saved } : DEFAULT_SOUND;
  } catch {
    return DEFAULT_SOUND;
  }
}

let engine: SoundEngine | null = null;

/** The page's engine, made on first use (null without Web Audio). */
function theEngine(): SoundEngine | null {
  engine ??= SoundEngine.create();
  return engine;
}

/** (Tests: forget the engine.) */
export function resetSoundEngine() { engine = null; }

/** Browsers start audio only after an interaction: resume on the next one. */
function resumeOnInteraction(e: SoundEngine) {
  const resume = () => {
    void e.resume();
    window.removeEventListener("pointerdown", resume);
    window.removeEventListener("keydown", resume);
  };
  window.addEventListener("pointerdown", resume);
  window.addEventListener("keydown", resume);
}

export function useGameSound({ game, play, timeline, replaying }: {
  game: Pick<Game, "neutral_site" | "stage">;
  play: PlaybackPlay | undefined;
  timeline: PlayTimeline | undefined;
  replaying: boolean;
}) {
  const [settings, setSettings] = useState<SoundSettings>(DEFAULT_SOUND);
  const [ready, setReady] = useState(false); // (settings read from the browser)
  useEffect(() => {
    setSettings(loadSettings()); // eslint-disable-line react-hooks/set-state-in-effect -- (browser-only storage)
    setReady(true);
  }, []);

  const update = useCallback((change: Partial<SoundSettings>) => {
    setSettings((current) => {
      const next = { ...current, ...change };
      try { localStorage.setItem(SOUND_KEY, JSON.stringify(next)); } catch { /* not remembered */ }
      // Turning sound on is a click: start the audio now, as browsers require.
      if (change.on) void theEngine()?.resume();
      return next;
    });
  }, []);

  // Sound on: the engine runs (once the browser allows); off, or leaving the viewer, quiets it.
  const on = ready && settings.on;
  useEffect(() => {
    if (!on) return;
    const e = theEngine();
    if (!e) return;
    if (e.state !== "running") resumeOnInteraction(e);
    void e.resume().catch(() => {});
    return () => {
      e.setCrowdLevel(0);
      void e.suspend().catch(() => {});
    };
  }, [on]);

  // The mix (volume, effects, crowd) follows the settings as they change.
  const { volume, effects, crowd } = settings;
  useEffect(() => {
    if (on) theEngine()?.setMix({ volume, effects, crowd });
  }, [on, volume, effects, crowd]);

  const cues = useMemo(() => (play && timeline ? soundCues(play, timeline, game) : []), [game, play, timeline]);
  const last = useRef(0);
  useEffect(() => { last.current = -1e-6; }, [cues]); // a new play starts from its beginning

  // The crowd's level for the situation.
  useEffect(() => {
    if (!on || !play) return;
    theEngine()?.setCrowdLevel(crowdLevel(play, game));
  }, [on, play, game]);

  const latest = useRef({ on, cues, replaying });
  useEffect(() => { latest.current = { on, cues, replaying }; });

  /** The playhead moved to `t`: play what it passed (a replay is quieter, without the
   * crowd's reaction). */
  const onTime = useCallback((t: number) => {
    const { on, cues: current, replaying: replay } = latest.current;
    const from = last.current;
    last.current = t;
    if (!on || !engine) return;
    for (const cue of dueCues(current, from, t)) {
      if (replay && cue.reaction) continue;
      engine.play(cue, replay ? 0.5 : 1);
    }
  }, []);

  return { settings, update, onTime };
}
