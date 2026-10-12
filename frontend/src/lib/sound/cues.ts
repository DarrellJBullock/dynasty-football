/**
 * What a play sounds like (docs/design/sound.md §3): which sounds, when (seconds into its
 * timeline) and how loud, from the play's moments and result; and how loud the crowd is.
 * Pure, so the sound of every kind of play is unit-tested; lib/sound/engine.ts makes them.
 */

import type { PlayTimeline } from "@/components/field/playback/timeline";
import type { Game, PlaybackPlay } from "@/lib/types";

export type SoundName =
  | "cadence" // the quarterback's call before the snap
  | "snap"
  | "catch"
  | "kick"
  | "hit" // pads: contact and ordinary tackles
  | "bigHit" // a sack, a takeaway, a hit for a loss
  | "whistle" // the end of the play
  | "flag" // the referee's whistle on a foul
  | "swell" // the crowd rising as a big play develops (lasts `duration`)
  | "cheer" // the home crowd's reaction
  | "groan";

export interface SoundCue {
  t: number; // seconds into the play's timeline
  sound: SoundName;
  gain: number; // 0–1
  duration?: number; // (a swell)
  /** The crowd's reaction (left out of instant replays). */
  reaction?: boolean;
}

type Side = "home" | "away";
const other = (side: Side): Side => (side === "home" ? "away" : "home");

/** Who a play was good for, and how much (null: nothing to react to). */
export function reaction(play: PlaybackPlay): { side: Side; big: boolean } | null {
  const r = play.result;
  const yards = typeof r.yards === "number" ? r.yards : 0;
  const ev = (t: string) => play.events.find((e) => e.t === t) as Record<string, unknown> | undefined;
  const offense = play.side;
  const defense = other(offense);
  if (r.defensive_td) return { side: defense, big: true };
  if (r.touchdown) return { side: offense, big: true };
  if (r.safety) return { side: defense, big: true };
  if (r.turnover_on_downs) return { side: defense, big: true };
  if (r.turnover) return { side: defense, big: true };
  const kick = ev("field_goal") ?? ev("extra_point") ?? ev("two_point");
  if (kick) return { side: kick.good ? offense : defense, big: ev("extra_point") === undefined };
  const kickoff = ev("kickoff");
  // An onside kick the kicking team (the "offense" of a kickoff) gets back.
  if (kickoff?.kind === "onside" && kickoff.recovered) return { side: offense, big: true };
  if (r.type === "sack") return { side: defense, big: false };
  if (r.type === "penalty") return null;
  if (yards >= 40) return { side: offense, big: true };
  if (yards >= 20) return { side: offense, big: false };
  if (r.first_down && (play.down ?? 0) >= 3) return { side: offense, big: false };
  return null;
}

/** The sounds of a play. `game` decides whose crowd it is (none at a neutral site). */
export function soundCues(play: PlaybackPlay, timeline: PlayTimeline, game: Pick<Game, "neutral_site">): SoundCue[] {
  const cues: SoundCue[] = [];
  const at = (kind: string) => timeline.moments.find((m) => m.kind === kind)?.t ?? null;
  const snap = at("snap");
  const scrimmage = play.down !== null && snap !== null;
  if (scrimmage) cues.push({ t: Math.max(0, snap - 0.7), sound: "cadence", gain: 0.5 });
  if (snap !== null) cues.push({ t: snap, sound: "snap", gain: 0.6 });

  const takeaway = Boolean(play.result.turnover) || play.result.type === "sack";
  const loss = typeof play.result.yards === "number" && play.result.yards < 0;
  for (const m of timeline.moments) {
    if (m.kind === "catch") cues.push({ t: m.t, sound: "catch", gain: 0.45 });
    if (m.kind === "kick") cues.push({ t: m.t, sound: "kick", gain: 0.9 });
    if (m.kind === "contact") cues.push({ t: m.t, sound: "hit", gain: 0.45 });
    if (m.kind === "tackle") {
      cues.push({ t: m.t, sound: takeaway || loss ? "bigHit" : "hit", gain: takeaway || loss ? 0.9 : 0.7 });
    }
    if (m.kind === "flag") cues.push({ t: m.t, sound: "flag", gain: 0.6 });
    if (m.kind === "whistle") cues.push({ t: m.t, sound: "whistle", gain: 0.55 });
  }

  // The crowd: it rises as a big play develops and reacts when it's over.
  const result = reaction(play);
  if (result) {
    const when = at("touchdown") ?? at("turnover") ?? at("tackle") ?? at("whistle") ?? timeline.duration;
    if (result.big) {
      const from = at("catch") ?? at("handoff") ?? snap ?? 0;
      if (when - from > 0.6) cues.push({ t: from, sound: "swell", gain: 0.6, duration: when - from, reaction: true });
    }
    const forHome = result.side === "home";
    const size = result.big ? 1 : 0.6;
    if (game.neutral_site) {
      cues.push({ t: when, sound: "cheer", gain: 0.5 * size, reaction: true });
    } else {
      cues.push({ t: when, sound: forHome ? "cheer" : "groan", gain: (forHome ? 1 : 0.7) * size, reaction: true });
    }
  }
  return cues.sort((a, b) => a.t - b.t);
}

/** How loud the crowd is during a play (0–1): louder late in close games and in the
 * playoffs. */
export function crowdLevel(play: PlaybackPlay, game: Pick<Game, "stage">): number {
  let level = 0.35;
  const margin = Math.abs(play.score.home - play.score.away);
  if (play.quarter >= 4 && margin <= 8) level += 0.2;
  if (play.quarter >= 5) level += 0.05; // overtime
  if (game.stage === "playoff") level += 0.15;
  return Math.min(0.8, level);
}

/** The cues the playhead passed going from `from` to `to` seconds (nothing on a jump: a
 * seek or a scrub shouldn't play everything in between). */
export function dueCues(cues: SoundCue[], from: number, to: number, maxStep = 0.3): SoundCue[] {
  if (to <= from || to - from > maxStep) return [];
  return cues.filter((c) => c.t > from && c.t <= to);
}
