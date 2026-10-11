/**
 * Instant replay (docs/design/broadcast.md §5): which plays get one, and how. Pure.
 *
 * A highlight play (a score, a turnover, a gain of 20 yards or more, a missed kick; the
 * Watch Mode rule) is replayed from just before the snap (or the kick) to just after the
 * whistle, at half speed, from a second angle: the skycam for passes, the reverse angle
 * from the far sideline for everything else.
 */

import { highlightReason } from "@/lib/highlights";
import type { PlaybackPlay } from "@/lib/types";
import type { ShotName } from "../layout";
import type { PlayTimeline } from "./timeline";

export interface ReplayPlan {
  from: number; // timeline seconds
  to: number;
  speed: number; // a share of the viewer's speed
  shot: ShotName;
  reason: string;
}

export const REPLAY_SPEED = 0.5;

export function replayPlan(play: PlaybackPlay, previous: PlaybackPlay | undefined,
                           timeline: PlayTimeline): ReplayPlan | null {
  const reason = highlightReason(play, previous);
  if (!reason) return null;
  const at = (kind: string) => timeline.moments.find((m) => m.kind === kind)?.t ?? null;
  const start = at("snap") ?? at("kick");
  const whistle = at("whistle") ?? timeline.duration;
  const pass = play.events.some((e) => e.t === "pass" && e.result !== "throwaway");
  return {
    from: Math.max(0, (start ?? 0) - 0.3),
    to: Math.min(timeline.duration, whistle + 0.3),
    speed: REPLAY_SPEED,
    shot: pass ? "skycam" : "reverse",
    reason,
  };
}
