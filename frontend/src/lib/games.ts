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

/** "W 26-17 vs Roadrunners", "L 10-24 @ Squall (OT)" */
export function describeResult(game: Game, teamId: number): string {
  const r = resultFor(game, teamId);
  const where = `${r.home ? "vs" : "@"} ${r.opponent.nickname}`;
  if (!r.outcome) return `Week ${game.week} ${where}`;
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
