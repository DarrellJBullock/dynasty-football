import type { PlaybackPlay } from "@/lib/types";

const BIG_PLAY = 20; // yards

/** Why a play makes the highlights, or null: points on the board, a turnover, a gain of 20
 * yards or more, or a missed field goal. */
export function highlightReason(play: PlaybackPlay, previous: PlaybackPlay | undefined): string | null {
  const before = previous?.score ?? { home: 0, away: 0 };
  if (play.score.home !== before.home || play.score.away !== before.away) return "score";
  const lostFumble = play.events.some((e) => e.t === "fumble" && e.lost);
  if (play.result.turnover || lostFumble || play.events.some((e) => e.t === "interception")) return "turnover";
  const gain = play.events.reduce((best, e) =>
    e.t === "rush" || e.t === "scramble" ? Math.max(best, e.yards)
      : e.t === "pass" && e.result === "complete" ? Math.max(best, e.yards) : best, 0);
  if (gain >= BIG_PLAY && play.result.type !== "penalty") return "big play";
  if (play.events.some((e) => e.t === "field_goal" && !e.good)) return "missed kick";
  return null;
}

/** The indexes of a game's highlight plays, in order. */
export function highlightIndexes(plays: PlaybackPlay[]): number[] {
  return plays.flatMap((play, i) => (highlightReason(play, plays[i - 1]) ? [i] : []));
}
