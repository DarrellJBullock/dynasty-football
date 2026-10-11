import type { Game, TeamSummary } from "@/lib/types";

export type Outcome = "W" | "L" | "T";

export interface TeamResult {
  outcome: Outcome | null; // null until the game is played
  home: boolean;
  opponent: TeamSummary;
  pointsFor: number | null;
  pointsAgainst: number | null;
}

/** A game from one team's point of view. */
export function resultFor(game: Game, teamId: number): TeamResult {
  const home = game.home.id === teamId;
  const pointsFor = home ? game.home_score : game.away_score;
  const pointsAgainst = home ? game.away_score : game.home_score;
  let outcome: Outcome | null = null;
  if (game.status === "final" && pointsFor !== null && pointsAgainst !== null) {
    outcome = pointsFor > pointsAgainst ? "W" : pointsFor < pointsAgainst ? "L" : "T";
  }
  return { outcome, home, opponent: home ? game.away : game.home, pointsFor, pointsAgainst };
}

/** When a game happens: "Week 3", or the playoff round ("Wild Card"). */
export function gameLabel(game: Game): string {
  return game.round_name ?? `Week ${game.week}`;
}

/** "W 26-17 vs Roadrunners", "L 10-24 @ Squall (OT)" */
export function describeResult(game: Game, teamId: number): string {
  const r = resultFor(game, teamId);
  const where = `${r.home ? "vs" : "@"} ${r.opponent.nickname}`;
  if (!r.outcome) return `${gameLabel(game)} ${where}`;
  return `${r.outcome} ${r.pointsFor}-${r.pointsAgainst} ${where}${game.overtime ? " (OT)" : ""}`;
}

export const OUTCOME_STYLES: Record<Outcome, string> = {
  W: "bg-emerald-400/15 text-emerald-300",
  L: "bg-rose-400/15 text-rose-300",
  T: "bg-slate-400/15 text-slate-300",
};

/** 1784 -> "29:44" */
export function formatPossession(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** A yard line in broadcast style from the offense's `ballOn` (yards from its own goal):
 * "HFD 34" in its own half, "ABQ 20" in the opponent's, "50" at midfield. */
export function formatSpot(ballOn: number, offense: string, defense: string): string {
  if (ballOn === 50) return "50";
  return ballOn < 50 ? `${offense} ${ballOn}` : `${defense} ${100 - ballOn}`;
}

/** The two calls on a snap: "Smash vs Cover 2", just the offense's when the defense's isn't
 * known, or null before named plays (SIM_VERSION 1.3). */
export function callLabel(play: string | null | undefined, defense: string | null | undefined): string | null {
  if (!play) return null;
  return defense ? `${play} vs ${defense}` : play;
}
