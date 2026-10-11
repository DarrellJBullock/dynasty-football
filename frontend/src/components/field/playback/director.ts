/**
 * The broadcast director (docs/design/broadcast.md §4): when to cut to which camera during
 * a play. Pure: a shot list from the play record and its timeline's moments. The camera
 * follows the ball; the director only picks the angle.
 */

import type { PlaybackPlay } from "@/lib/types";
import type { ShotName } from "../layout";
import { SNAP } from "./choreograph";
import type { PlayTimeline } from "./timeline";

export interface Cue { t: number; shot: ShotName }

/** The shortest a shot is held before the next cut (touchdowns cut at once). */
export const MIN_SHOT = 1.2;
const DEEP_PASS = 25; // air yards

export function shotList(play: PlaybackPlay, timeline: PlayTimeline): Cue[] {
  const at = (kind: string) => timeline.moments.find((m) => m.kind === kind)?.t ?? null;
  const has = (t: string) => play.events.some((e) => e.t === t);
  const whistle = at("whistle") ?? timeline.duration;
  const cues: Cue[] = [{ t: 0, shot: "wide" }];
  const cut = (t: number | null, shot: ShotName, force = false) => {
    const last = cues[cues.length - 1];
    if (t === null || shot === last.shot || t < last.t) return;
    if (!force && t - last.t < MIN_SHOT) return;
    cues.push({ t, shot });
  };

  if (has("field_goal") || has("extra_point")) {
    cut((at("snap") ?? SNAP) - 0.2, "endzone", true); // behind the kicker, through the uprights
  } else if (has("kickoff") || has("punt")) {
    cut(at("kick"), "sideline", true); // track the ball downfield
    cut(at("tackle") ?? whistle, "tight");
  } else if (at("snap") !== null) {
    cut(at("snap"), "sideline", true);
    const pass = play.events.find((e) => e.t === "pass");
    if (pass && pass.t === "pass" && pass.air >= DEEP_PASS && pass.result !== "throwaway") {
      cut(at("throw"), "wide"); // pull back to see the receiver
      cut(at("catch") ?? at("contact"), "sideline");
    }
    if (at("touchdown") === null) cut(at("tackle") === null ? null : at("tackle")! - 0.3, "tight");
  } else {
    cut(at("flag"), "tight"); // a pre-snap foul: on the flag
  }
  cut(at("touchdown"), "tight", true);
  cut(whistle + 0.3, "tight");
  return cues;
}

/** The shot at `t`: the latest cue at or before it. */
export function shotAt(cues: Cue[], t: number): ShotName {
  let shot = cues[0]?.shot ?? "sideline";
  for (const cue of cues) {
    if (cue.t > t) break;
    shot = cue.shot;
  }
  return shot;
}
