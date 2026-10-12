import Link from "next/link";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatPhase } from "@/lib/format";
import type { Game, ScheduleWeek } from "@/lib/types";
import { SimControls } from "./SimControls";

export function ScheduleView({ schedule, teamId }: { schedule: ScheduleWeek; teamId: number }) {
  const { season, week } = schedule;
  const weeks = Array.from({ length: season.weeks }, (_, i) => i + 1);
  const mine = schedule.games.filter((g) => g.home.id === teamId || g.away.id === teamId);
  const others = schedule.games.filter((g) => !mine.includes(g));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">
            {season.year} {formatPhase(season.phase)}
          </div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Schedule</h1>
        </div>
        <SimControls season={season} teamId={teamId} />
      </div>

      <nav aria-label="Weeks" className="panel flex gap-1 overflow-x-auto p-2">
        {weeks.map((w) => {
          const played = w < season.current_week;
          return (
            <Link
              key={w}
              href={`/schedule?week=${w}`}
              aria-current={w === week ? "page" : undefined}
              className={`shrink-0 rounded-md px-3 py-1.5 font-display text-sm font-semibold ${
                w === week ? "bg-gold text-ink-950" : played ? "text-chalk hover:bg-white/5" : "text-mist hover:bg-white/5"
              }`}
            >
              Wk {w}
            </Link>
          );
        })}
        <Link href="/playoffs" className="shrink-0 rounded-md px-3 py-1.5 font-display text-sm font-semibold text-gold hover:bg-white/5">
          Playoffs →
        </Link>
      </nav>

      <section aria-label={`Week ${week} games`} className="space-y-3">
        <h2 className="eyebrow">Week {week}</h2>
        <ul className="grid gap-3 md:grid-cols-2">
          {[...mine, ...others].map((game) => (
            <li key={game.id}>
              <GameCard game={game} highlight={mine.includes(game)}
                coachable={mine.includes(game) && game.status !== "final" && week === season.current_week
                  && ["preseason", "regular_season", "playoffs"].includes(season.phase)} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** A game: the card opens the box score; final games can be watched, and the franchise's
 * game this week can be coached. (Separate links, so none is nested in another.) */
function GameCard({ game, highlight, coachable }: { game: Game; highlight: boolean; coachable: boolean }) {
  const final = game.status === "final";
  const awayWon = final && game.away_score! > game.home_score!;
  const homeWon = final && game.home_score! > game.away_score!;
  const matchup = `${game.away.full_name} at ${game.home.full_name}`;
  return (
    <div className={`panel relative flex items-center gap-4 px-4 py-3 hover:border-white/15 ${highlight ? "ring-1 ring-gold/40" : ""}`}>
      <Link href={`/games/${game.id}`} aria-label={matchup}
        className="absolute inset-0 rounded-[inherit] focus-visible:outline-2 focus-visible:outline-gold" />
      <div className="min-w-0 flex-1 space-y-1.5">
        {[
          { team: game.away, score: game.away_score, won: awayWon },
          { team: game.home, score: game.home_score, won: homeWon },
        ].map(({ team, score, won }) => (
          <div key={team.id} className="flex items-center gap-3">
            <TeamCrest team={team} size={22} />
            <span className={`flex-1 truncate text-sm ${final && !won ? "text-mist" : "font-medium"}`}>
              {team.full_name}
            </span>
            {final && <span className={`stat-number text-lg ${won ? "" : "text-mist"}`}>{score}</span>}
          </div>
        ))}
      </div>
      <div className="flex w-16 flex-col items-end gap-1 text-right">
        <span className="text-xs uppercase tracking-wider text-mist">
          {final ? (game.overtime ? "Final/OT" : "Final") : "Upcoming"}
        </span>
        {final && (
          <Link href={`/games/${game.id}/watch?auto=1`} aria-label={`Watch ${matchup}`}
            className="relative inline-flex min-h-6 items-center text-xs font-semibold text-gold hover:underline">
            Watch
          </Link>
        )}
        {coachable && (
          <Link href="/coach" aria-label={`Coach ${matchup}`}
            className="relative inline-flex min-h-6 items-center text-xs font-semibold text-gold hover:underline">
            Coach
          </Link>
        )}
      </div>
    </div>
  );
}
