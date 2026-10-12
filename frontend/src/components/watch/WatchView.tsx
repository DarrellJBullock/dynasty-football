"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { choreographGame } from "@/components/field/playback/choreograph";
import { BroadcastOverlay, ReplayBadge } from "@/components/broadcast/BroadcastOverlay";
import { PlayClock } from "@/components/field/playback/clock";
import { PLAY_CAMERAS, type CameraChoice } from "@/components/field/layout";
import { shotList } from "@/components/field/playback/director";
import { replayPlan } from "@/components/field/playback/replay";
import { useInstantReplay } from "@/components/field/playback/useInstantReplay";
import { callLabel, formatSpot } from "@/lib/games";
import { highlightIndexes } from "@/lib/highlights";
import type { GamePlayback, PlaybackPlay } from "@/lib/types";
import { usePrefersReducedMotion } from "@/lib/motion";
import { unityBuild } from "@/lib/unity";

// WebGL only exists in the browser, so the scene is never server-rendered.
const PlayScene = dynamic(() => import("@/components/field/playback/PlayScene"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-turf/10" />,
});

// The Unity renderer (docs/design/depth-and-unity.md §4), when its build is installed.
const UnityPlayScene = dynamic(() => import("@/components/field/unity/UnityPlayScene"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-turf/10" />,
});

type Renderer = "classic" | "unity";
const RENDERERS: { key: Renderer; label: string }[] = [
  { key: "classic", label: "Classic" }, { key: "unity", label: "Unity" },
];
const RENDERER_KEY = "dynasty.renderer"; // the visitor's choice, in localStorage

const SPEEDS = [0.5, 1, 2];
const AUTO_ADVANCE_PAUSE = 900; // ms between plays when playing the drive
const UI_STEP = 0.1; // seconds of playhead between scrubber updates

function quarterLabel(q: number): string {
  return q <= 4 ? `Q${q}` : q === 5 ? "OT" : `OT${q - 4}`;
}

function ordinal(n: number): string {
  return ["", "1st", "2nd", "3rd", "4th"][n] ?? `${n}th`;
}

/** "HFD 1st & 10 at HFD 34", or what kind of snap it is when there's no down. */
function situation(play: PlaybackPlay, playback: GamePlayback): string {
  const { home, away } = playback.game;
  const [offense, defense] = play.side === "home" ? [home, away] : [away, home];
  if (play.events.some((e) => e.t === "kickoff")) return `${offense.abbreviation} kicks off`;
  if (play.down == null || play.ball_on == null) return `${offense.abbreviation} conversion try`;
  const toGo = play.ball_on + (play.distance ?? 0) >= 100 ? "Goal" : play.distance;
  return `${offense.abbreviation} ${ordinal(play.down)} & ${toGo} at ${
    formatSpot(play.ball_on, offense.abbreviation, defense.abbreviation)}`;
}

/**
 * The 3D viewer for one game: a play at a time, with play/pause, a scrubber marked with
 * the play's moments, speed, previous/next, auto-advance through the game, and cameras.
 */
export function WatchView({ playback, initialPlay, initialAuto = false, initialHighlights = false }: {
  playback: GamePlayback;
  initialPlay?: number;
  initialAuto?: boolean; // play straight through
  initialHighlights?: boolean; // only the highlights
}) {
  const plays = playback.plays;
  const choreographed = useMemo(() => choreographGame(playback), [playback]);
  const highlightList = useMemo(() => highlightIndexes(plays), [plays]);
  const [highlights, setHighlights] = useState(initialHighlights && highlightList.length > 0);
  const [index, setIndex] = useState(() => {
    const requested = plays.findIndex((p) => p.n === initialPlay);
    if (requested >= 0) return requested;
    return initialHighlights && highlightList.length ? highlightList[0] : 0;
  });
  const [time, setTime] = useState(0);
  const [playing, setPlayingState] = useState(true);
  const [speed, setSpeedState] = useState(1);
  const [camera, setCamera] = useState<CameraChoice>("broadcast");
  const [renderer, setRendererState] = useState<Renderer>("classic");
  const [unityInstalled, setUnityInstalled] = useState(false);
  const [unityProblem, setUnityProblem] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    void unityBuild().then((files) => {
      if (!live || !files) return;
      setUnityInstalled(true);
      try {
        if (localStorage.getItem(RENDERER_KEY) === "unity") setRendererState("unity");
      } catch { /* storage blocked: start on Classic */ }
    });
    return () => { live = false; };
  }, []);
  const setRenderer = (choice: Renderer) => {
    setRendererState(choice);
    setUnityProblem(null);
    try { localStorage.setItem(RENDERER_KEY, choice); } catch { /* not remembered */ }
  };
  // Unity failed (no WebGL 2, a broken download…): back to Classic, here and next time.
  const onUnityError = useCallback((message: string) => {
    setRendererState("classic");
    setUnityProblem(message);
    try { localStorage.setItem(RENDERER_KEY, "classic"); } catch { /* not remembered */ }
  }, []);
  const [follow, setFollow] = useState(true);
  const [auto, setAuto] = useState(initialAuto);
  // Instant replays, unless the visitor asked for less motion (then off until turned on).
  const reducedMotion = usePrefersReducedMotion();
  const [replaysChoice, setReplays] = useState<boolean | null>(null);
  const replays = replaysChoice ?? !reducedMotion;
  const [clock] = useState(() => new PlayClock());
  const shown = useRef(0);

  const current = choreographed[index];
  const play = current?.play;
  const timeline = current?.timeline;
  const duration = timeline?.duration ?? 0;
  const cues = useMemo(() => (play && timeline ? shotList(play, timeline) : []), [play, timeline]);
  const ended = time >= duration - 1e-6;

  const setPlaying = useCallback((value: boolean) => {
    clock.setPlaying(value);
    setPlayingState(value);
  }, [clock]);

  // Instant replay of highlight plays, from a second angle at half speed.
  const plan = useMemo(() => (play && timeline ? replayPlan(play, plays[index - 1], timeline) : null),
                       [index, play, plays, timeline]);
  const onSeek = useCallback((t: number) => {
    shown.current = t;
    setTime(t);
    setPlayingState(clock.playing);
  }, [clock]);
  const replay = useInstantReplay({ clock, plan, enabled: replays, ended, playKey: index, duration, onSeek });

  // The plays being stepped through: all of them, or just the highlights.
  const reel = highlights ? highlightList : null;
  const neighbor = useCallback((from: number, step: 1 | -1): number | null => {
    if (!reel) {
      const next = from + step;
      return next >= 0 && next < plays.length ? next : null;
    }
    const candidates = step === 1 ? reel.filter((i) => i > from) : reel.filter((i) => i < from).reverse();
    return candidates[0] ?? null;
  }, [plays.length, reel]);

  const { cancel: cancelReplay } = replay;
  const goTo = useCallback((next: number | null) => {
    if (next === null || next < 0 || next >= plays.length) return;
    cancelReplay();
    clock.seek(0);
    shown.current = 0;
    setIndex(next);
    setTime(0);
    setPlaying(true);
  }, [cancelReplay, clock, plays.length, setPlaying]);

  // Keep the URL in step, so the address bar links back to exactly this.
  useEffect(() => {
    const n = plays[index]?.n;
    if (n === undefined) return;
    window.history.replaceState(null, "",
      `?play=${n}${highlights ? "&highlights=1" : ""}${auto ? "&auto=1" : ""}`);
  }, [auto, highlights, index, plays]);

  const toggleHighlights = (on: boolean) => {
    setHighlights(on);
    if (on && !highlightList.includes(index)) goTo(highlightList.find((i) => i > index) ?? highlightList[0]);
  };

  const { track: trackReplay } = replay;
  const onTick = useCallback((t: number, justEnded: boolean) => {
    if (justEnded) setPlayingState(false);
    if (justEnded || Math.abs(t - shown.current) >= UI_STEP) {
      shown.current = t;
      setTime(t);
    }
    trackReplay(t);
  }, [trackReplay]);

  const togglePlay = useCallback(() => {
    if (!clock.playing && clock.time >= duration - 1e-6) {
      clock.seek(0);
      shown.current = 0;
      setTime(0);
    }
    setPlaying(!clock.playing);
  }, [clock, duration, setPlaying]);

  const scrub = (t: number) => {
    cancelReplay();
    setPlaying(false);
    clock.seek(t);
    shown.current = t;
    setTime(t);
  };

  const setSpeed = (value: number) => {
    clock.setSpeed(value);
    setSpeedState(value);
  };

  // Straight through: on to the next play (or highlight) after a short pause.
  const next = neighbor(index, 1);
  const previous = neighbor(index, -1);
  const replayDone = replay.settled;
  useEffect(() => {
    if (!auto || !ended || !replayDone || next === null) return;
    const timer = setTimeout(() => goTo(next), AUTO_ADVANCE_PAUSE);
    return () => clearTimeout(timer);
  }, [auto, ended, next, goTo, replayDone]);

  // Space plays and pauses; the arrow keys step between plays.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea, select, button, a, summary")) return;
      if (event.key === " ") {
        event.preventDefault();
        togglePlay();
      } else if (event.key === "ArrowRight") {
        goTo(next);
      } else if (event.key === "ArrowLeft") {
        goTo(previous);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, next, previous, togglePlay]);

  // Keep the current play in view in the list.
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [index]);

  const { game } = playback;
  if (!play || !timeline) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link href={`/games/${game.id}`} className="text-sm text-gold hover:underline">← Box score</Link>
        <p className="panel p-6 text-center text-sm text-mist">
          {playback.log_compacted
            ? "Play-by-play isn't kept for this older game: only its scoring plays and injuries, on the box score."
            : "This game has no plays to watch."}
        </p>
      </div>
    );
  }

  const moment = [...timeline.moments].reverse().find((m) => m.t <= time + 1e-6);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/games/${game.id}`} className="text-sm text-gold hover:underline">← Box score</Link>
        <h1 className="eyebrow">
          {game.away.full_name} at {game.home.full_name} · {game.round_name ?? `Week ${game.week}`}
        </h1>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="panel overflow-hidden" aria-label="Play viewer">
          <div className="relative aspect-video w-full bg-ink-950">
            {renderer === "unity" ? (
              <UnityPlayScene playback={playback} timeline={timeline} clock={clock}
                camera={replay.replaying ? "broadcast" : camera}
                cues={replay.replaying && plan ? [{ t: 0, shot: plan.shot }] : cues}
                follow={follow} onTick={onTick} onError={onUnityError} />
            ) : (
              <PlayScene playback={playback} timeline={timeline} clock={clock}
                camera={replay.replaying ? "broadcast" : camera}
                cues={replay.replaying && plan ? [{ t: 0, shot: plan.shot }] : cues}
                follow={follow} onTick={onTick} />
            )}
            <BroadcastOverlay playback={playback} index={index} timeline={timeline} time={time}
              replay={replay.replaying} />
            {replay.replaying && <ReplayBadge key={plan?.from} onSkip={replay.skip} />}
            {moment && (
              <p className="absolute left-3 top-3 rounded-lg bg-ink-950/75 px-3 py-1.5 text-sm font-semibold backdrop-blur"
                role="status">
                {moment.text}
              </p>
            )}
          </div>

          <div className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="btn btn-ghost" onClick={() => goTo(previous)}
                disabled={previous === null}>‹ Previous play</button>
              <button type="button" className="btn btn-primary min-w-20" onClick={togglePlay}>
                {playing ? "Pause" : ended ? "Replay" : "Play"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => goTo(next)}
                disabled={next === null}>Next play ›</button>
              <div role="group" aria-label="Speed" className="ml-2 flex gap-1">
                {SPEEDS.map((s) => (
                  <button key={s} type="button" aria-pressed={speed === s}
                    className={`rounded-md px-2 py-1 text-xs font-semibold ${
                      speed === s ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
                    onClick={() => setSpeed(s)}>
                    {s}×
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div role="group" aria-label="Camera" className="flex gap-1 rounded-lg bg-white/[0.03] p-1">
                {PLAY_CAMERAS.map(({ key, label }) => (
                  <button key={key} type="button" aria-pressed={camera === key}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                      camera === key ? "bg-gold text-ink-950" : "text-mist hover:text-chalk"}`}
                    onClick={() => setCamera(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <div role="group" aria-label="Renderer" className="flex gap-1 rounded-lg bg-white/[0.03] p-1">
                {RENDERERS.map(({ key, label }) => (
                  <button key={key} type="button" aria-pressed={renderer === key}
                    disabled={key === "unity" && !unityInstalled}
                    title={key === "unity" && !unityInstalled ? "The Unity viewer isn't installed on this server" : undefined}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-semibold disabled:opacity-40 ${
                      renderer === key ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
                    onClick={() => setRenderer(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <button type="button" aria-pressed={follow} disabled={camera === "broadcast"}
                title={camera === "broadcast" ? "The broadcast camera always follows the ball" : undefined}
                className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                  follow ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"} disabled:opacity-40`}
                onClick={() => setFollow(!follow)}>
                Follow ball
              </button>
              <label className="ml-auto flex items-center gap-2 text-xs text-mist">
                <input type="checkbox" checked={highlights} disabled={highlightList.length === 0}
                  onChange={(e) => toggleHighlights(e.target.checked)} />
                Highlights only ({highlightList.length})
              </label>
              <label className="flex items-center gap-2 text-xs text-mist">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
                Play straight through
              </label>
              <label className="flex items-center gap-2 text-xs text-mist">
                <input type="checkbox" checked={replays} onChange={(e) => {
                  if (!e.target.checked) replay.cancel();
                  setReplays(e.target.checked);
                }} />
                Instant replays
              </label>
            </div>
            {unityProblem && (
              <p role="alert" className="text-xs text-amber-300">
                The Unity viewer stopped: {unityProblem} Showing the classic viewer.
              </p>
            )}

            <div className="relative">
              <input type="range" aria-label="Play timeline" className="w-full accent-gold"
                min={0} max={duration} step={0.01} value={Math.min(time, duration)}
                aria-valuetext={`${time.toFixed(1)} of ${duration.toFixed(1)} seconds`}
                onChange={(e) => scrub(Number(e.target.value))} />
              <ol className="pointer-events-none relative h-3" aria-label="Moments">
                {timeline.moments.map((m, i) => (
                  <li key={i} title={m.text}
                    className={`absolute top-0 h-2 w-0.5 rounded ${m.kind === "flag" ? "bg-yellow-400"
                      : m.kind === "touchdown" || m.kind === "turnover" ? "bg-gold" : "bg-mist/60"}`}
                    style={{ left: `${(m.t / duration) * 100}%` }}>
                    <span className="sr-only">{m.text}</span>
                  </li>
                ))}
              </ol>
            </div>

            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wider text-mist">
                {highlights && reel ? `Highlight ${reel.indexOf(index) + 1} of ${reel.length} · ` : ""}
                Play {play.n} of {plays.length} · {situation(play, playback)}
              </p>
              <p className="text-sm" data-testid="play-text">{play.text}</p>
              {callLabel(play.play_name, play.defense_name) && (
                <p className="text-xs text-mist" data-testid="play-call">
                  {callLabel(play.play_name, play.defense_name)}
                </p>
              )}
              {play.approximate && (
                <p className="text-xs text-amber-300">
                  Approximate lineup: this game was played before lineups were recorded, so the
                  players shown come from today&apos;s depth chart.
                </p>
              )}
            </div>
          </div>
        </section>

        <aside className="panel flex max-h-[38rem] flex-col p-0" aria-label="Plays">
          <h2 className="eyebrow px-4 pb-2 pt-4">{highlights ? "Highlights" : "Plays"}</h2>
          <ol ref={listRef} className="flex-1 divide-y divide-white/[0.04] overflow-y-auto">
            {plays.map((p, i) => (reel && !reel.includes(i) ? null :
              <li key={p.n}>
                <button type="button" aria-current={i === index ? "true" : undefined}
                  className={`grid w-full grid-cols-[3.5rem_minmax(0,1fr)] gap-2 px-4 py-2 text-left text-xs ${
                    i === index ? "bg-gold/10 text-chalk" : "text-mist hover:bg-white/[0.03] hover:text-chalk"}`}
                  onClick={() => goTo(i)}>
                  <span className="tabular-nums">{quarterLabel(p.quarter)} {p.clock}</span>
                  <span className="truncate">{p.text}</span>
                </button>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}
