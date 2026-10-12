"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { PerspectiveCamera, Vector3 } from "three";
import { cameraShot, type CameraPreset, type ShotName } from "./layout";
import { usePrefersReducedMotion } from "@/lib/motion";

const EASE = 3.5; // higher is snappier

/** A directed shot for this frame: which camera, framing what (field coordinates). */
export interface Direction { shot: ShotName; x: number; y: number }

/**
 * Moves the camera toward a preset's shot, easing between presets. With `direct`, the
 * director picks the shot every frame instead: a new shot is a cut (no easing), and the
 * camera eases only as it follows within a shot.
 */
export function CameraRig({ preset, focus, direction = 1, follow, direct }: {
  preset: CameraPreset;
  focus?: number; // field x to frame
  direction?: 1 | -1;
  /** Called every frame for the field x to frame instead (following the ball). */
  follow?: () => number;
  /** Called every frame for the director's shot (overrides `preset`). */
  direct?: () => Direction;
}) {
  const target = useRef<Vector3 | null>(null);
  const goal = useRef(new Vector3());
  const lastShot = useRef<ShotName | null>(null);

  // Less motion: no orbiting, and every move is a cut.
  const still = usePrefersReducedMotion();

  useFrame((state, delta) => {
    const camera = state.camera;
    const time = still ? 0 : state.clock.elapsedTime;
    const directed = direct?.();
    const shot = directed
      ? cameraShot(directed.shot, directed.x, direction, time, directed.y)
      : cameraShot(preset, follow ? follow() : focus, direction, time);
    const aim = new Vector3(...shot.target);
    goal.current.set(...shot.position);
    const cut = still || (directed !== undefined && directed.shot !== lastShot.current);
    lastShot.current = directed?.shot ?? null;
    if (cut) {
      camera.position.copy(goal.current);
      target.current = aim;
    } else {
      const k = 1 - Math.exp(-EASE * delta);
      camera.position.lerp(goal.current, k);
      target.current = target.current ? target.current.lerp(aim, k) : aim;
    }
    camera.lookAt(target.current);
    if (camera instanceof PerspectiveCamera) {
      camera.fov = cut ? shot.fov : camera.fov + (shot.fov - camera.fov) * (1 - Math.exp(-EASE * delta));
      camera.updateProjectionMatrix();
    }
  });
  return null;
}
