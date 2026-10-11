"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { PerspectiveCamera, Vector3 } from "three";
import { cameraShot, type CameraPreset } from "./layout";

const EASE = 3.5; // higher is snappier

/** Moves the camera toward a preset's shot, easing between presets. */
export function CameraRig({ preset, focus, direction = 1 }: {
  preset: CameraPreset;
  focus?: number; // field x to frame
  direction?: 1 | -1;
}) {
  const target = useRef<Vector3 | null>(null);
  const goal = useRef(new Vector3());

  useFrame((state, delta) => {
    const camera = state.camera;
    const shot = cameraShot(preset, focus, direction, state.clock.elapsedTime);
    const k = 1 - Math.exp(-EASE * delta);
    goal.current.set(...shot.position);
    camera.position.lerp(goal.current, k);
    const aim = new Vector3(...shot.target);
    target.current = target.current ? target.current.lerp(aim, k) : aim;
    camera.lookAt(target.current);
    if (camera instanceof PerspectiveCamera) {
      camera.fov += (shot.fov - camera.fov) * k;
      camera.updateProjectionMatrix();
    }
  });
  return null;
}
