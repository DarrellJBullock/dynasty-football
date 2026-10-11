/**
 * The play timeline (docs/design/play-playback.md §3): everything the 3D viewer needs to
 * show one play, in field coordinates (yards) over time (seconds from the start of the
 * play). Built by the choreographer; sampled here. Pure.
 */

import type { Vec3 } from "../layout";
import { blend, pose, runPhase, type JointAngles, type Pose } from "../players/poses";

export interface PathKey { t: number; x: number; y: number }

/** A pose from `t` until the next key. `span` times one-off motions (a throw's windup and
 * release); `face` pins the facing (radians) instead of following the motion. */
export interface PoseKey { t: number; pose: Pose; span?: number; face?: number }

export interface TimelinePlayer {
  id: number; // negative: not a named player (kick units, stand-ins)
  side: "offense" | "defense";
  teamId: number;
  role: string;
  name: string;
  number: number;
  position: string;
  heightIn: number;
  weightLb: number;
  facing: number; // at the start
  path: PathKey[];
  poses: PoseKey[];
}

export type BallSegment =
  | { kind: "held"; from: number; to: number; player: number }
  | { kind: "flight"; from: number; to: number; start: Vec3; end: Vec3; apex: number }
  | { kind: "rest"; from: number; to: number; at: Vec3 };

export type MomentKind = "snap" | "handoff" | "throw" | "catch" | "kick" | "contact" | "tackle"
  | "touchdown" | "turnover" | "flag" | "whistle";

export interface Moment { t: number; kind: MomentKind; text: string }

export interface PlayTimeline {
  version: 1;
  duration: number;
  direction: 1 | -1; // the offense (kicking team on kickoffs) drives toward +x or −x
  los: number | null; // field x of the line of scrimmage
  firstDownLine: number | null;
  players: TimelinePlayer[];
  ball: BallSegment[];
  moments: Moment[];
  flag: { t: number; x: number; y: number } | null;
}

// ---------- sampling ----------

function segment<T extends { t: number }>(keys: T[], t: number): number {
  let lo = 0;
  let hi = keys.length - 1;
  if (t <= keys[0].t) return 0;
  if (t >= keys[hi].t) return hi;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (keys[mid].t <= t) lo = mid; else hi = mid;
  }
  return lo;
}

export function positionAt(path: PathKey[], t: number): { x: number; y: number } {
  const i = segment(path, t);
  const a = path[i];
  const b = path[i + 1];
  if (!b || t <= a.t) return { x: a.x, y: a.y };
  const k = Math.min(1, (t - a.t) / Math.max(1e-6, b.t - a.t));
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
}

/** Yards covered by time `t` (drives the run cycle). */
export function distanceAt(path: PathKey[], t: number): number {
  let total = 0;
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];
    if (t <= a.t) break;
    const full = Math.hypot(b.x - a.x, b.y - a.y);
    const share = t >= b.t ? 1 : (t - a.t) / Math.max(1e-6, b.t - a.t);
    total += full * share;
  }
  return total;
}

/** Speed (yards/second) and heading at `t`. */
export function velocityAt(path: PathKey[], t: number): { speed: number; heading: number | null } {
  const i = segment(path, t);
  const a = path[i];
  const b = path[i + 1];
  if (!b || t < a.t || t >= b.t) return { speed: 0, heading: null };
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 0.05) return { speed: 0, heading: null };
  return { speed: dist / Math.max(1e-6, b.t - a.t), heading: Math.atan2(dy, dx) };
}

const BLEND_TIME = 0.18;

export function anglesAt(player: TimelinePlayer, t: number): JointAngles {
  const i = segment(player.poses, t);
  const angles = (k: PoseKey) => {
    const { speed } = velocityAt(player.path, t);
    const progress = k.span ? (t - k.t) / k.span : 0;
    return pose(k.pose, runPhase(distanceAt(player.path, t)), progress, Math.min(1, speed / 7));
  };
  const current = angles(player.poses[i]);
  const since = t - player.poses[i].t;
  if (i > 0 && since < BLEND_TIME) return blend(angles(player.poses[i - 1]), current, since / BLEND_TIME);
  return current;
}

/** Facing at `t`: pinned by the pose, else the direction of travel, else the last one. */
export function facingAt(player: TimelinePlayer, t: number): number {
  const key = player.poses[segment(player.poses, t)];
  if (key.face !== undefined) return key.face;
  const { heading } = velocityAt(player.path, t);
  if (heading !== null) return heading;
  // Standing still: keep the heading of the last movement before `t`.
  for (let i = segment(player.path, t); i > 0; i--) {
    const a = player.path[i - 1];
    const b = player.path[i];
    if (Math.hypot(b.x - a.x, b.y - a.y) > 0.05) return Math.atan2(b.y - a.y, b.x - a.x);
  }
  return player.facing;
}

/** The ball's position at `t`. `carrier` resolves where a holding player's hands are. */
export function ballAt(timeline: PlayTimeline, t: number,
                       carrier: (id: number, t: number) => Vec3): Vec3 {
  const segments = timeline.ball;
  const current = segments.find((s) => t >= s.from && t < s.to) ?? segments[segments.length - 1];
  switch (current.kind) {
    case "held": return carrier(current.player, Math.min(t, current.to));
    case "rest": return current.at;
    case "flight": {
      const k = Math.min(1, Math.max(0, (t - current.from) / Math.max(1e-6, current.to - current.from)));
      const [x0, y0, z0] = current.start;
      const [x1, y1, z1] = current.end;
      return [x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, z0 + (z1 - z0) * k + 4 * current.apex * k * (1 - k)];
    }
  }
}

/** Where a player's hands hold the ball: tucked at his side, a little in front. */
export function handsAt(player: TimelinePlayer, t: number): Vec3 {
  const { x, y } = positionAt(player.path, t);
  const facing = facingAt(player, t);
  const lying = anglesAt(player, t).lie;
  return [x + Math.cos(facing) * 0.35, y + Math.sin(facing) * 0.35, 1.05 - lying * 0.85];
}
