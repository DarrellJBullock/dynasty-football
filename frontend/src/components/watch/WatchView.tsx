"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { choreographGame } from "@/components/field/playback/choreograph";
import { PlayClock } from "@/components/field/playback/clock";
import { CAMERA_PRESETS, type CameraPreset } from "@/components/field/layout";
import { formatSpot } from "@/lib/games";
import type { GamePlayback, PlaybackPlay } from "@/lib/types";

// WebGL only exists in the browser, so the scene is never server-rendered.
const PlayScene = dynamic(() => import("@/components/field/playback/PlayScene"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-turf/10" />,
});

const CAMERAS = CAMERA_PRESETS.filter((c) => c.key !== "overview");
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
export function WatchView({ playback, initialPlay = 1 }: { playback: GamePlayback; initialPlay?: number }) {
  const plays = playback.plays;
  const choreographed = useMemo(() => choreographGame(playback), [playback]);
  const [index, setIndex] = useState(() => Math.max(0, plays.findIndex((p) => p.n === initialPlay)));
  const [time, setTime] = useState(0);
  const [playing, setPlayingState] = useState(true);
  const [speed, setSpeedState] = useState(1);
  const [camera, setCamera] = useState<CameraPreset>("sideline");
  const [follow, setFollow] = useState(true);
  const [auto, setAuto] = useState(false);
  const [clock] = useState(() => new PlayClock());
  const shown = useRef(0);

  const current = choreographed[index];
  const play = current?.play;
  const timeline = current?.timeline;
  const duration = timeline?.duration ?? 0;
  const ended = time >= duration - 1e-6;

  const setPlaying = useCallback((value: boolean) => {
    clock.setPlaying(value);
    setPlayingState(value);
  }, [clock]);

  const goTo = useCallback((next: number) => {
    if (next < 0 || next >= plays.length) return;
    clock.seek(0);
    shown.current = 0;
    setIndex(next);
    setTime(0);
    setPlaying(true);
    window.history.replaceState(null, "", `?play=${plays[next].n}`);
  }, [clock, plays, setPlaying]);

  const onTick = useCallback((t: number, justEnded: boolean) => {
    if (justEnded) setPlayingState(false);
    if (justEnded || Math.abs(t - shown.current) >= UI_STEP) {
      shown.current = t;
      setTime(t);
    }
  }, []);

  const togglePlay = useCallback(() => {
    if (!clock.playing && clock.time >= duration - 1e-6) {
      clock.seek(0);
      shown.current = 0;
      setTime(0);
    }
    setPlaying(!clock.playing);
  }, [clock, duration, setPlaying]);

  const scrub = (t: number) => {
    setPlaying(false);
    clock.seek(t);
    shown.current = t;
    setTime(t);
  };

  const setSpeed = (value: number) => {
    clock.setSpeed(value);
    setSpeedState(value);
  };

  // Play the drive: on to the next play after a short pause.
  useEffect(() => {
    if (!auto || !ended || index >= plays.length - 1) return;
    const timer = setTimeout(() => goTo(index + 1), AUTO_ADVANCE_PAUSE);
    return () => clearTimeout(timer);
  }, [auto, ended, index, plays.length, goTo]);

  // Space plays and pauses; the arrow keys step between plays.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea, select, button, a, summary")) return;
      if (event.key === " ") {
        event.preventDefault();
        togglePlay();
      } else if (event.key === "ArrowRight") {
        goTo(index + 1);
      } else if (event.key === "ArrowLeft") {
        goTo(index - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, index, togglePlay]);

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
        <p className="panel p-6 text-center text-sm text-mist">This game has no plays to watch.</p>
      </div>
    );
  }

  const before = index > 0 ? plays[index - 1].score : { home: 0, away: 0 };
  const score = ended ? play.score : before;
  const moment = [...timeline.moments].reverse().find((m) => m.t <= time + 1e-6);

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/games/${game.id}`} className="text-sm text-gold hover:underline">← Box score</Link>
        <span className="eyebrow">
          {game.away.full_name} at {game.home.full_name} · {game.round_name ?? `Week ${game.week}`}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="panel overflow-hidden" aria-label="Play viewer">
          <div className="relative aspect-video w-full bg-ink-950">
            <PlayScene playback={playback} timeline={timeline} clock={clock} camera={camera}
              follow={follow} onTick={onTick} />
            <div className="absolute left-3 top-3 flex items-center gap-3 rounded-lg bg-ink-950/75 px-3 py-1.5 text-sm backdrop-blur"
              aria-label="Score" role="group">
              <span className="font-semibold">{game.away.abbreviation} <span className="tabular-nums">{score.away}</span></span>
              <span className="font-semibold">{game.home.abbreviation} <span className="tabular-nums">{score.home}</span></span>
              <span className="text-xs tabular-nums text-mist">{quarterLabel(play.quarter)} {play.clock}</span>
            </div>
            {moment && (
              <p className="absolute bottom-3 left-3 rounded-lg bg-ink-950/75 px-3 py-1.5 text-sm font-semibold backdrop-blur"
                role="status">
                {moment.text}
              </p>
            )}
          </div>

          <div className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="btn btn-ghost" onClick={() => goTo(index - 1)}
                disabled={index === 0}>‹ Previous play</button>
              <button type="button" className="btn btn-primary min-w-20" onClick={togglePlay}>
                {playing ? "Pause" : ended ? "Replay" : "Play"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => goTo(index + 1)}
                disabled={index === plays.length - 1}>Next play ›</button>
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
                {CAMERAS.map(({ key, label }) => (
                  <button key={key} type="button" aria-pressed={camera === key}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
                      camera === key ? "bg-gold text-ink-950" : "text-mist hover:text-chalk"}`}
                    onClick={() => setCamera(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <button type="button" aria-pressed={follow}
                className={`rounded-md px-2 py-1 text-[11px] font-semibold ${
                  follow ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
                onClick={() => setFollow(!follow)}>
                Follow ball
              </button>
              <label className="ml-auto flex items-center gap-2 text-xs text-mist">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
                Play the drive
              </label>
            </div>

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
                Play {play.n} of {plays.length} · {situation(play, playback)}
              </p>
              <p className="text-sm" data-testid="play-text">{play.text}</p>
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
          <h2 className="eyebrow px-4 pb-2 pt-4">Plays</h2>
          <ol ref={listRef} className="flex-1 divide-y divide-white/[0.04] overflow-y-auto">
            {plays.map((p, i) => (
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
