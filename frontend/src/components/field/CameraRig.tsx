"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { PerspectiveCamera } from "three";
import { CameraFollower, type Direction } from "./cameraFollow";
import type { CameraPreset } from "./layout";
import { usePrefersReducedMotion } from "@/lib/motion";

export type { Direction } from "./cameraFollow";

/**
 * Moves the camera toward a preset's shot, easing between presets. With `direct`, the
 * director picks the shot every frame instead: a new shot is a cut (no easing), and the
 * camera eases only as it follows within a shot (cameraFollow.ts).
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
  const follower = useRef(new CameraFollower());

  // Less motion: no orbiting, and every move is a cut.
  const still = usePrefersReducedMotion();

  useFrame((state, delta) => {
    const camera = state.camera;
    const shot = follower.current.step({
      preset, focus, direction, follow: follow?.(), directed: direct?.(),
      time: still ? 0 : state.clock.elapsedTime,
    }, delta, still);
    camera.position.set(...shot.position);
    camera.lookAt(...shot.target);
    if (camera instanceof PerspectiveCamera) {
      camera.fov = shot.fov;
      camera.updateProjectionMatrix();
    }
  });
  return null;
}
