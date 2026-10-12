/**
 * Broadcast graphics (docs/design/broadcast.md §3): what the score bug and banners show at
 * each instant of a play. Pure: everything comes from the play record and its timeline.
 */

import { SNAP } from "@/components/field/playback/choreograph";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import { penaltyName } from "@/lib/penalties";
import type { PlaybackPlay } from "@/lib/types";

const BANNER_HOLD = 2.2; // seconds a banner stays up

type Score = { home: number; away: number };

export function clockSeconds(label: string): number {
  const [minutes, seconds] = label.split(":").map(Number);
  return minutes * 60 + seconds;
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function momentTime(timeline: PlayTimeline, kind: string): number | null {
  return timeline.moments.find((m) => m.kind === kind)?.t ?? null;
}

/** When the action ends: the whistle (or the end of the timeline). */
function whistle(timeline: PlayTimeline): number {
  return momentTime(timeline, "whistle") ?? timeline.duration;
}

/** The game clock at `t` seconds into the play: the clock at the snap until the snap,
 * then running down second by second through the play's recorded seconds, reaching them
 * at the whistle. */
export function gameClockAt(play: PlaybackPlay, timeline: PlayTimeline, t: number): number {
  const start = clockSeconds(play.clock);
  const runs = play.seconds ?? 0;
  const action = Math.max(0.5, whistle(timeline) - SNAP);
  const share = Math.min(1, Math.max(0, (t - SNAP) / action));
  return Math.max(0, start - Math.floor(runs * share + 1e-9));
}

/** The play clock before the snap (a few seconds left as the offense sets), or null once
 * the ball is snapped, and for kicks and conversions. */
export function playClockAt(play: PlaybackPlay, t: number): number | null {
  if (play.down == null || t >= SNAP) return null;
  const left = 4 + ((play.n * 7) % 11); // where the count was when they set: 4-14
  return Math.max(1, left - Math.floor(t));
}

/** The score shown at `t`: the score before the play until the points go up (the
 * touchdown, or the whistle on a kick or safety). */
export function scoreAt(play: PlaybackPlay, previous: PlaybackPlay | undefined, timeline: PlayTimeline,
                        t: number): Score {
  const before = previous?.score ?? { home: 0, away: 0 };
  const changed = before.home !== play.score.home || before.away !== play.score.away;
  if (!changed) return play.score;
  const when = momentTime(timeline, "touchdown") ?? whistle(timeline);
  return t >= when ? play.score : before;
}

function ordinal(n: number): string {
  return ["", "1st", "2nd", "3rd", "4th"][n] ?? `${n}th`;
}

/** "3rd & 4", "1st & Goal", or what kind of snap it is. */
export function downText(play: PlaybackPlay): string {
  if (play.events.some((e) => e.t === "kickoff")) return "Kickoff";
  if (play.events.some((e) => e.t === "two_point")) return "2-pt try";
  if (play.events.some((e) => e.t === "extra_point")) return "PAT";
  if (play.down == null || play.distance == null || play.ball_on == null) return "";
  const toGo = play.ball_on + play.distance >= 100 ? "Goal" : String(play.distance);
  return `${ordinal(play.down)} & ${toGo}`;
}

export type BannerTone = "gold" | "red" | "flag" | "plain";
export interface Banner { t: number; text: string; tone: BannerTone }

/** The banners a play earns, at their moments. */
export function bannersFor(play: PlaybackPlay, timeline: PlayTimeline): Banner[] {
  const at = (kind: string) => momentTime(timeline, kind);
  const end = whistle(timeline);
  const banners: Banner[] = [];
  const add = (t: number | null, text: string, tone: BannerTone) => {
    if (t !== null) banners.push({ t, text, tone });
  };
  const events = play.events;
  const result = play.result;
  for (const e of events) {
    if (e.t === "kickoff" && e.kind === "onside") {
      add(at("turnover") ?? at("catch") ?? end, e.recovered ? "Onside kick recovered!" : "Onside kick", e.recovered ? "gold" : "plain");
    } else if (e.t === "sack") {
      add(at("tackle") ?? end, "Sack", "red");
    } else if (e.t === "interception") {
      add(at("turnover") ?? end, "Interception", "red");
    } else if (e.t === "fumble" && e.lost) {
      add(at("turnover") ?? end, "Fumble", "red");
    } else if (e.t === "field_goal") {
      add(end, e.good ? "Field goal good" : "No good", e.good ? "gold" : "red");
    } else if (e.t === "two_point") {
      add(end, e.good ? "Two-point try good" : "Two-point try fails", e.good ? "gold" : "red");
    } else if (e.t === "penalty") {
      add(at("flag") ?? end, `Flag · ${penaltyName(e.kind)}`, "flag");
    }
  }
  if (result.touchdown) add(at("touchdown") ?? end, "Touchdown", "gold");
  else if (result.safety) add(end, "Safety", "red");
  else if (result.turnover_on_downs) add(end, "Turnover on downs", "red");
  else if (result.first_down && result.type !== "penalty") add(at("tackle") ?? end, "First down", "plain");
  return banners.sort((a, b) => a.t - b.t);
}

/** The banner up at `t`, if any: the latest one shown in the last few seconds. */
export function bannerAt(banners: Banner[], t: number): Banner | null {
  return [...banners].reverse().find((b) => t >= b.t && t < b.t + BANNER_HOLD) ?? null;
}
