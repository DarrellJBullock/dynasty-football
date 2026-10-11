"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { Group } from "three";
import type { GamePlayback } from "@/lib/types";
import { CameraRig } from "../CameraRig";
import { cameraShot, toScene, WIDTH, type CameraPreset } from "../layout";
import { kit, skinTone, type Kit } from "../players/kit";
import { Football, PlayerFigure, type PlayerFrame } from "../players/PlayerFigure";
import { build } from "../players/poses";
import { Stadium } from "../Stadium";
import type { PlayClock } from "./clock";
import { anglesAt, ballAt, facingAt, handsAt, positionAt, type PlayTimeline,
         type TimelinePlayer } from "./timeline";

export interface PlaySceneProps {
  playback: GamePlayback;
  timeline: PlayTimeline;
  clock: PlayClock;
  camera: CameraPreset;
  follow: boolean;
  /** Every frame: the playhead, and whether it just reached the end. */
  onTick: (time: number, ended: boolean) => void;
}

/** One play in 3D: the stadium, all 22 players and the ball, posed from the timeline. */
export default function PlayScene({ playback, timeline, clock, camera, follow, onTick }: PlaySceneProps) {
  const { home, away } = playback.game;
  const start = cameraShot(camera, timeline.los ?? 60, timeline.direction);
  const kits = useMemo(() => new Map<number, Kit>([[home.id, kit(home, true)], [away.id, kit(away, false)]]),
                       [home, away]);
  const ball = useMemo(() => {
    const players = new Map(timeline.players.map((p) => [p.id, p]));
    return (t: number) => ballAt(timeline, t, (id, at) => handsAt(players.get(id)!, at));
  }, [timeline]);

  return (
    <Canvas
      camera={{ position: start.position, fov: start.fov, far: 600 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      aria-label="3D play"
    >
      <Ticker clock={clock} duration={timeline.duration} onTick={onTick} />
      <CameraRig preset={camera} focus={timeline.los ?? ball(0)[0]} direction={timeline.direction}
        follow={follow ? () => ball(clock.time)[0] : undefined} />
      <Stadium field={{ primary: home.primary_color, secondary: home.secondary_color,
                        nickname: home.nickname, abbreviation: home.abbreviation }}
        lineOfScrimmage={timeline.los} firstDownLine={timeline.firstDownLine} />
      {timeline.players.map((player) => (
        <TimelineFigure key={`${player.side}-${player.role}`} player={player} clock={clock}
          kit={kits.get(player.teamId) ?? kit(home, true)} />
      ))}
      <Football driver={() => {
        const t = clock.time;
        const [x, y, z] = ball(t);
        const flying = timeline.ball.some((s) => s.kind === "flight" && t >= s.from && t < s.to);
        return { x, y, z, spin: flying ? t * 25 : 0 };
      }} />
      {timeline.flag && <Flag flag={timeline.flag} clock={clock} />}
    </Canvas>
  );
}

/** Advances the playhead. Mounted first, so the figures read this frame's time. */
function Ticker({ clock, duration, onTick }: {
  clock: PlayClock; duration: number; onTick: PlaySceneProps["onTick"];
}) {
  useFrame((_, delta) => {
    const ended = clock.advance(delta, duration);
    onTick(clock.time, ended);
  });
  return null;
}

function TimelineFigure({ player, clock, kit: colors }: {
  player: TimelinePlayer; clock: PlayClock; kit: Kit;
}) {
  const figure = useMemo(() => build(player.heightIn, player.weightLb), [player.heightIn, player.weightLb]);
  const driver = (): PlayerFrame => {
    const t = clock.time;
    return { ...positionAt(player.path, t), facing: facingAt(player, t), angles: anglesAt(player, t) };
  };
  return <PlayerFigure build={figure} kit={colors} number={player.number} skin={skinTone(player.id)}
    driver={driver} />;
}

/** A penalty flag, thrown at its moment: it flutters down to the turf. */
function Flag({ flag, clock }: { flag: { t: number; x: number; y: number }; clock: PlayClock }) {
  const ref = useRef<Group>(null);
  useFrame(() => {
    const group = ref.current;
    if (!group) return;
    const since = clock.time - flag.t;
    group.visible = since >= 0;
    const k = Math.min(1, Math.max(0, since / 0.7));
    const [sx, , sz] = toScene(flag.x, Math.min(Math.max(flag.y, 0), WIDTH));
    group.position.set(sx, 2.4 * (1 - k * k) + 0.02, sz);
    group.rotation.set(Math.sin(since * 9) * 0.6 * (1 - k), since * 3 * (1 - k), 0);
  });
  return (
    <group ref={ref} visible={false}>
      <mesh>
        <boxGeometry args={[0.4, 0.02, 0.4]} />
        <meshStandardMaterial color="#facc15" roughness={0.8} />
      </mesh>
    </group>
  );
}
