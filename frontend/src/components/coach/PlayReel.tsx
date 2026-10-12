"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BroadcastOverlay, ReplayBadge } from "@/components/broadcast/BroadcastOverlay";
import type { Choreography } from "@/components/field/playback/choreograph";
import { PlayClock } from "@/components/field/playback/clock";
import { PLAY_CAMERAS, type CameraChoice } from "@/components/field/layout";
import { shotList } from "@/components/field/playback/director";
import { replayPlan } from "@/components/field/playback/replay";
import { useInstantReplay } from "@/components/field/playback/useInstantReplay";
import { callLabel } from "@/lib/games";
import type { GamePlayback } from "@/lib/types";
import { usePrefersReducedMotion } from "@/lib/motion";
import { RendererSwitch, UnityPlayScene, UnityProblem, useRenderer } from "@/components/field/unity/renderer";
import { Captions } from "@/components/sound/Captions";
import { SoundControls } from "@/components/sound/SoundControls";
import { commentaryFor } from "@/lib/commentary";
import { useGameSound } from "@/lib/sound/useGameSound";

// WebGL only exists in the browser, so the scene is never server-rendered.
const PlayScene = dynamic(() => import("@/components/field/playback/PlayScene"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-turf/10" />,
});

const BETWEEN_PLAYS = 700; // ms pause before the next play in the reel

/**
 * The plays a call produced, one after another in 3D (the snap, plus any kickoff or extra
 * point after it), then holding on the last frame. Remount it (a new `key`) for a new reel.
 */
export function PlayReel({ playback, reel }: { playback: GamePlayback; reel: Choreography[] }) {
  const [index, setIndex] = useState(0);
  const [ended, setEnded] = useState(false);
  const [camera, setCamera] = useState<CameraChoice>("broadcast");
  const [clock] = useState(() => new PlayClock());
  // Classic or Unity, as chosen on the Watch page or here (one Unity runs for the page, so
  // each new reel picks it straight up).
  const { renderer, setRenderer, installed, problem, onUnityError } = useRenderer();
  const [time, setTime] = useState(0); // for the broadcast graphics, a tenth of a second at a time
  const shown = useRef(0);
  const last = reel.length - 1;
  const current = reel[Math.min(index, last)];
  const cues = useMemo(() => (current ? shotList(current.play, current.timeline) : []), [current]);
  const playIndex = current ? playback.plays.findIndex((p) => p.n === current.play.n) : -1;

  // Instant replays of highlights, but only in a reel of several plays (a drive the AI
  // called): a single call's play goes straight back to the call screen.
  const plan = useMemo(() => (current ? replayPlan(current.play, playback.plays[playIndex - 1], current.timeline) : null),
                       [current, playIndex, playback.plays]);
  const onSeek = useCallback((t: number) => {
    shown.current = t;
    setTime(t);
  }, []);
  const reducedMotion = usePrefersReducedMotion(); // (no replays for less motion)
  const instant = useInstantReplay({ clock, plan, enabled: reel.length > 1 && !reducedMotion, ended, playKey: index,
                                     duration: current?.timeline.duration ?? 0, onSeek });
  const { track, settled, cancel } = instant;
  const sound = useGameSound({ game: playback.game, play: current?.play, timeline: current?.timeline,
                               replaying: instant.replaying });
  const { onTime: soundTime } = sound;
  const commentary = useMemo(() => (current && playIndex >= 0 ? commentaryFor(playback, playIndex, current.timeline) : []),
                             [current, playIndex, playback]);

  const onTick = useCallback((t: number, justEnded: boolean) => {
    soundTime(t);
    if (justEnded) setEnded(true);
    if (justEnded || Math.abs(t - shown.current) >= 0.1) {
      shown.current = t;
      setTime(t);
    }
    track(t);
  }, [soundTime, track]);

  // On to the next play in the reel after a short pause (and any replay).
  useEffect(() => {
    if (!ended || index >= last || !settled) return;
    const timer = setTimeout(() => {
      clock.seek(0);
      clock.setPlaying(true);
      shown.current = 0;
      setTime(0);
      setEnded(false);
      setIndex(index + 1);
    }, BETWEEN_PLAYS);
    return () => clearTimeout(timer);
  }, [clock, ended, index, last, settled]);

  const skip = () => {
    cancel();
    setIndex(last);
    clock.seek(reel[last].timeline.duration);
    clock.setPlaying(false);
    shown.current = reel[last].timeline.duration;
    setTime(reel[last].timeline.duration);
    setEnded(true);
  };

  const replay = () => {
    clock.seek(0);
    clock.setPlaying(true);
    shown.current = 0;
    setTime(0);
    setEnded(false);
  };

  if (!current) return null;
  const { play } = current;
  const done = ended && index >= last;
  return (
    <section className="panel overflow-hidden" aria-label="Last play">
      <div className="relative aspect-video w-full bg-ink-950">
        {renderer === "unity" ? (
          <UnityPlayScene playback={playback} timeline={current.timeline} clock={clock}
            camera={instant.replaying ? "broadcast" : camera}
            cues={instant.replaying && plan ? [{ t: 0, shot: plan.shot }] : cues}
            follow onTick={onTick} onError={onUnityError} />
        ) : (
          <PlayScene playback={playback} timeline={current.timeline} clock={clock}
            camera={instant.replaying ? "broadcast" : camera}
            cues={instant.replaying && plan ? [{ t: 0, shot: plan.shot }] : cues}
            follow onTick={onTick} />
        )}
        <BroadcastOverlay playback={playback} timeline={current.timeline} time={time}
          index={playIndex} replay={instant.replaying} />
        {instant.replaying && <ReplayBadge key={index} onSkip={instant.skip} />}
        {sound.settings.captions && !instant.replaying && <Captions lines={commentary} time={time} />}
        <div role="group" aria-label="Camera"
          className="absolute right-3 top-3 flex gap-1 rounded-lg bg-ink-950/70 p-1 backdrop-blur">
          {PLAY_CAMERAS.map(({ key, label }) => (
            <button key={key} type="button" aria-pressed={camera === key}
              className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                camera === key ? "bg-gold text-ink-950" : "text-mist hover:text-chalk"}`}
              onClick={() => setCamera(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-start gap-3 p-4">
        <div className="min-w-0 flex-1">
          {reel.length > 1 && (
            <p className="text-xs uppercase tracking-wider text-mist">Play {index + 1} of {reel.length}</p>
          )}
          <p className="text-sm" data-testid="reel-text">{play.text}</p>
          {callLabel(play.play_name, play.defense_name) && (
            <p className="text-xs text-mist">{callLabel(play.play_name, play.defense_name)}</p>
          )}
          <UnityProblem problem={problem} />
        </div>
        <SoundControls settings={sound.settings} onChange={sound.update} />
        <RendererSwitch renderer={renderer} installed={installed} onChange={setRenderer} />
        {done ? (
          <button type="button" className="btn btn-ghost px-3 py-1 text-xs" onClick={replay}>Replay</button>
        ) : (
          <button type="button" className="btn btn-ghost px-3 py-1 text-xs" onClick={skip}>Skip</button>
        )}
      </div>
    </section>
  );
}
