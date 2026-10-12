/**
 * The camera's motion, frame by frame: toward a preset's shot (easing), or the broadcast
 * director's (a new shot is a cut; within a shot it eases as it follows). Pure, so the
 * three.js rig (CameraRig.tsx) and the Unity viewer move the camera exactly alike.
 */

import { cameraShot, type CameraPreset, type CameraShot, type ShotName, type Vec3 } from "./layout";

const EASE = 3.5; // higher is snappier

/** A directed shot for this frame: which camera, framing what (field coordinates). */
export interface Direction { shot: ShotName; x: number; y: number }

export interface CameraAim {
  preset: CameraPreset;
  focus?: number; // field x to frame
  direction: 1 | -1;
  /** The field x to frame instead (following the ball). */
  follow?: number;
  /** The director's shot (overrides `preset`). */
  directed?: Direction;
  time: number; // seconds of real time (turns the overview)
}

export class CameraFollower {
  position: Vec3 | null = null;
  target: Vec3 | null = null;
  fov = 0;
  private lastShot: ShotName | null = null;

  /** Moves on by `delta` seconds toward this frame's shot; `still` (less motion) always cuts. */
  step(aim: CameraAim, delta: number, still: boolean): CameraShot {
    const { directed, direction } = aim;
    const shot = directed
      ? cameraShot(directed.shot, directed.x, direction, aim.time, directed.y)
      : cameraShot(aim.preset, aim.follow ?? aim.focus, direction, aim.time);
    const cut = still || this.position === null || this.target === null
      || (directed !== undefined && directed.shot !== this.lastShot);
    this.lastShot = directed?.shot ?? null;
    if (cut) {
      this.position = [...shot.position];
      this.target = [...shot.target];
      this.fov = shot.fov;
    } else {
      const k = 1 - Math.exp(-EASE * delta);
      this.position = lerp(this.position!, shot.position, k);
      this.target = lerp(this.target!, shot.target, k);
      this.fov += (shot.fov - this.fov) * k;
    }
    return { position: this.position, target: this.target, fov: this.fov };
  }
}

function lerp(a: Vec3, b: Vec3, k: number): Vec3 {
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
}
