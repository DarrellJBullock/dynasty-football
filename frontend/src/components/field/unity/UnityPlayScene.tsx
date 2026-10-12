"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CameraFollower } from "../cameraFollow";
import { canvasSize, drawField } from "../fieldTexture";
import { kit } from "../players/kit";
import { shotAt } from "../playback/director";
import type { PlaySceneProps } from "../playback/PlayScene";
import { ballAt, handsAt } from "../playback/timeline";
import { usePrefersReducedMotion } from "@/lib/motion";
import { leaseUnity, unityBuild, type UnityLease, type UnityPlayer } from "@/lib/unity";

export interface UnityPlaySceneProps extends PlaySceneProps {
  /** Unity couldn't start or failed (the page falls back to the classic viewer). */
  onError: (message: string) => void;
}

/**
 * One play drawn by Unity (docs/design/depth-and-unity.md §4): the same props as the
 * classic PlayScene. The page's clock, director and camera rig run here, every frame, and
 * Unity is told the time and the camera; it draws the play from the timeline. It borrows
 * the page's one Unity (lib/unity.ts leaseUnity) and gives it back when it goes away.
 */
export default function UnityPlayScene(props: UnityPlaySceneProps) {
  const { playback, timeline } = props;
  const container = useRef<HTMLDivElement>(null);
  const lease = useRef<UnityLease | null>(null);
  const latest = useRef(props);
  useEffect(() => { latest.current = props; });
  const [player, setPlayer] = useState<UnityPlayer | null>(null);
  const [progress, setProgress] = useState(0);
  const [plays, setPlays] = useState(0); // plays Unity has loaded (it says so each time)
  const still = usePrefersReducedMotion();
  const stillRef = useRef(still);
  useEffect(() => { stillRef.current = still; }, [still]);

  // Borrow the page's Unity (starting it the first time), and give it back on the way out.
  useEffect(() => {
    let cancelled = false;
    const fail = (message: string) => { if (!cancelled) latest.current.onError(message); };
    void unityBuild().then((files) => {
      if (cancelled) return;
      if (!files) {
        fail("The Unity viewer isn't installed on this server.");
        return;
      }
      lease.current = leaseUnity(container.current!, files, (event) => {
        if (event.type === "error") fail(event.detail);
        if (event.type === "loaded") setPlays((n) => n + 1);
      }, setProgress);
      lease.current.player
        .then((unity) => { if (!cancelled) setPlayer(unity); })
        .catch((error: Error) => fail(error.message));
    });
    return () => {
      cancelled = true;
      lease.current?.release();
      lease.current = null;
    };
  }, []);

  // Each game: the field, painted as the classic viewer paints it, and the home crowd
  // (only if Unity doesn't already have this game's).
  const { home, away } = playback.game;
  useEffect(() => {
    if (!player || !lease.current) return;
    void lease.current.setField(`${home.id}`, () => paintedField({
      primary: home.primary_color, secondary: home.secondary_color,
      nickname: home.nickname, abbreviation: home.abbreviation,
    }), [home.primary_color, home.secondary_color]);
  }, [player, home]);

  // Each play: its timeline and both teams' uniforms.
  useEffect(() => {
    if (!player) return;
    player.loadPlay(timeline, { [home.id]: kit(home, true), [away.id]: kit(away, false) });
  }, [player, home, away, timeline]);

  const ball = useMemo(() => {
    const players = new Map(timeline.players.map((p) => [p.id, p]));
    return (t: number) => ballAt(timeline, t, (id, at) => handsAt(players.get(id)!, at));
  }, [timeline]);
  const ballRef = useRef(ball);
  useEffect(() => { ballRef.current = ball; }, [ball]);

  // Every frame: advance the playhead, pick the camera, tell Unity.
  useEffect(() => {
    if (!player) return;
    const follower = new CameraFollower();
    const started = performance.now();
    let last = started;
    let frame = 0;
    const step = (now: number) => {
      const p = latest.current;
      const delta = (now - last) / 1000;
      last = now;
      const ended = p.clock.advance(delta, p.timeline.duration);
      p.onTick(p.clock.time, ended);
      const t = p.clock.time;
      const [x, y] = ballRef.current(t);
      const broadcast = p.camera === "broadcast";
      const preset = p.camera === "broadcast" ? "sideline" : p.camera;
      const shot = follower.step({
        preset, focus: p.timeline.los ?? ballRef.current(0)[0],
        direction: p.timeline.direction, follow: !broadcast && p.follow ? x : undefined,
        directed: broadcast ? { shot: shotAt(p.cues ?? [], t), x, y } : undefined,
        time: stillRef.current ? 0 : (now - started) / 1000,
      }, delta, stillRef.current);
      player.setFrame(t, shot);
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [player]);

  return (
    <div className="relative h-full w-full" data-renderer="unity"
      data-unity-state={player ? "ready" : "loading"} data-unity-plays={plays}>
      {/* (The page's one Unity canvas is moved in here while this viewer is shown.) */}
      <div ref={container} className="h-full w-full" />
      {!player && (
        <p className="absolute inset-0 grid place-items-center text-sm text-mist" role="status">
          Loading the Unity viewer… {Math.round(progress * 100)}%
        </p>
      )}
    </div>
  );
}

/** The field surface as a base64 PNG (fieldTexture.ts, like the classic Stadium), or null
 * where there's no 2D canvas. */
function paintedField(style: Parameters<typeof drawField>[1]): string | null {
  const canvas = document.createElement("canvas");
  const { width, height } = canvasSize();
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  drawField(ctx, style);
  return canvas.toDataURL("image/png").split(",")[1] ?? null;
}
