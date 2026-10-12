"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CameraFollower } from "../cameraFollow";
import { canvasSize, drawField } from "../fieldTexture";
import { kit } from "../players/kit";
import { shotAt } from "../playback/director";
import type { PlaySceneProps } from "../playback/PlayScene";
import { ballAt, handsAt } from "../playback/timeline";
import { usePrefersReducedMotion } from "@/lib/motion";
import { startUnity, unityBuild, type UnityPlayer } from "@/lib/unity";

export interface UnityPlaySceneProps extends PlaySceneProps {
  /** Unity couldn't start or failed (the page falls back to the classic viewer). */
  onError: (message: string) => void;
}

/**
 * One play drawn by Unity (docs/design/depth-and-unity.md §4): the same props as the
 * classic PlayScene. The page's clock, director and camera rig run here, every frame, and
 * Unity is told the time and the camera; it draws the play from the timeline.
 */
export default function UnityPlayScene(props: UnityPlaySceneProps) {
  const { playback, timeline } = props;
  const canvas = useRef<HTMLCanvasElement>(null);
  const latest = useRef(props);
  useEffect(() => { latest.current = props; });
  const [player, setPlayer] = useState<UnityPlayer | null>(null);
  const [progress, setProgress] = useState(0);
  const [plays, setPlays] = useState(0); // plays Unity has loaded (it says so each time)
  const still = usePrefersReducedMotion();
  const stillRef = useRef(still);
  useEffect(() => { stillRef.current = still; }, [still]);

  // Start Unity once, and quit it when the scene goes away.
  useEffect(() => {
    let cancelled = false;
    let started: UnityPlayer | null = null;
    const fail = (message: string) => { if (!cancelled) latest.current.onError(message); };
    unityBuild()
      .then((files) => {
        if (!files) throw new Error("The Unity viewer isn't installed on this server.");
        return startUnity(canvas.current!, files, (event) => {
          if (event.type === "error") fail(event.detail);
          if (event.type === "loaded") setPlays((n) => n + 1);
        }, setProgress);
      })
      .then((unity) => {
        if (cancelled) { void unity.quit(); return; }
        started = unity;
        setPlayer(unity);
      })
      .catch((error: Error) => fail(error.message));
    return () => {
      cancelled = true;
      void started?.quit();
    };
  }, []);

  // Each game: the field, painted as the classic viewer paints it, and the home crowd.
  const { home, away } = playback.game;
  useEffect(() => {
    if (!player) return;
    const image = paintedField({ primary: home.primary_color, secondary: home.secondary_color,
                                 nickname: home.nickname, abbreviation: home.abbreviation });
    if (image) player.setField(image, [home.primary_color, home.secondary_color]);
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
      {/* (Unity's runtime finds its canvas by id; there's one viewer on a page.) */}
      <canvas ref={canvas} id="unity-canvas" className="h-full w-full" role="img" aria-label="3D play"
        tabIndex={-1} />
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
