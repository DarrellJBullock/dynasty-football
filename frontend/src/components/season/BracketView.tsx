import Link from "next/link";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatRecord } from "@/lib/format";
import type { Game, PlayoffConference, PlayoffsOut, TeamSummary } from "@/lib/types";
import { SimControls } from "./SimControls";

export function BracketView({ bracket, teamId, canRun = true }: {
  bracket: PlayoffsOut; teamId: number; canRun?: boolean;
}) {
  const seedOf = new Map<number, number>();
  const conferenceOf = new Map<number, string>();
  for (const conference of bracket.conferences) {
    for (const s of conference.seeds) {
      seedOf.set(s.team.id, s.seed);
      conferenceOf.set(s.team.id, conference.conference);
    }
  }
  const projected = bracket.status === "projected";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{bracket.season.year} postseason</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Playoffs</h1>
          {projected && (
            <p className="mt-1 text-sm text-mist">
              Projected — if the season ended today. The bracket is set when the regular season ends.
            </p>
          )}
        </div>
        <SimControls season={bracket.season} teamId={teamId} canRun={canRun} />
      </div>

      {bracket.champion && <ChampionBanner team={bracket.champion} year={bracket.season.year} />}

      <div className="grid gap-6 md:grid-cols-2">
        {bracket.conferences.map((conference) => (
          <SeedList key={conference.conference} conference={conference} teamId={teamId} />
        ))}
      </div>

      {!projected && (
        <section aria-label="Bracket" className="panel overflow-x-auto p-5">
          <div className="grid min-w-[900px] gap-4" style={{ gridTemplateColumns: `repeat(${bracket.rounds.length}, minmax(0, 1fr))` }}>
            {bracket.rounds.map((round) => (
              <div key={round.round} className="space-y-3" aria-label={round.name} role="group">
                <h2 className="eyebrow">{round.name}</h2>
                {round.games.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-white/10 p-3 text-xs text-mist">TBD</p>
                ) : (
                  groupByConference(round.games, conferenceOf).map(([conference, games]) => (
                    <div key={conference} className="space-y-2">
                      {bracket.conferences.length > 1 && round.games.length > 1 && (
                        <div className="text-[10px] uppercase tracking-wider text-mist">{conference}</div>
                      )}
                      {games.map((game) => (
                        <MatchupCard key={game.id} game={game} seedOf={seedOf} teamId={teamId} />
                      ))}
                    </div>
                  ))
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function groupByConference(games: Game[], conferenceOf: Map<number, string>): [string, Game[]][] {
  const groups = new Map<string, Game[]>();
  for (const game of games) {
    const key = game.neutral_site ? "Championship" : conferenceOf.get(game.home.id) ?? "";
    groups.set(key, [...(groups.get(key) ?? []), game]);
  }
  return [...groups];
}

function ChampionBanner({ team, year }: { team: TeamSummary; year: number }) {
  return (
    <section aria-label="Champion"
      className="panel relative flex items-center gap-5 overflow-hidden p-6"
      style={{ background: `linear-gradient(110deg, ${team.primary_color}55, transparent 60%)` }}>
      <TeamCrest team={team} size={72} />
      <div>
        <div className="eyebrow text-gold">{year} champions</div>
        <div className="font-display text-4xl font-extrabold uppercase tracking-wide">{team.full_name}</div>
      </div>
      <svg viewBox="0 0 24 24" className="ml-auto hidden h-16 w-16 text-gold sm:block" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden>
        <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4Z" />
        <path d="M7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3" />
      </svg>
    </section>
  );
}

function SeedList({ conference, teamId }: { conference: PlayoffConference; teamId: number }) {
  return (
    <section className="panel p-5" aria-label={`${conference.conference} seeds`}>
      <h2 className="eyebrow mb-3">{conference.conference}</h2>
      <ol className="space-y-1.5">
        {conference.seeds.map((s) => (
          <li key={s.team.id} data-eliminated={s.eliminated || undefined}
            className={`flex items-center gap-3 rounded-md px-2 py-1 text-sm ${
              s.team.id === teamId ? "bg-gold/[0.08]" : ""} ${s.eliminated ? "opacity-45" : ""}`}>
            <span className="stat-number w-5 text-right text-mist">{s.seed}</span>
            <TeamCrest team={s.team} size={20} />
            <span className="flex-1 truncate">{s.team.full_name}</span>
            {s.division_winner && (
              <span className="rounded bg-white/[0.06] px-1.5 text-[10px] font-semibold uppercase text-mist">Div</span>
            )}
            {s.seed === 1 && conference.seeds.length % 2 === 1 && (
              <span className="rounded bg-gold/10 px-1.5 text-[10px] font-semibold uppercase text-gold">Bye</span>
            )}
            <span className="w-12 text-right tabular-nums text-mist">{formatRecord(s)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function MatchupCard({ game, seedOf, teamId }: { game: Game; seedOf: Map<number, number>; teamId: number }) {
  const final = game.status === "final";
  const rows = [
    { team: game.away, score: game.away_score, won: final && game.away_score! > game.home_score! },
    { team: game.home, score: game.home_score, won: final && game.home_score! > game.away_score! },
  ];
  const mine = game.home.id === teamId || game.away.id === teamId;
  return (
    <Link href={`/games/${game.id}`} aria-label={`${game.away.full_name} at ${game.home.full_name}`}
      className={`block rounded-lg border bg-white/[0.02] p-2.5 hover:border-white/20 ${mine ? "border-gold/40" : "border-white/5"}`}>
      {rows.map(({ team, score, won }) => (
        <div key={team.id} className={`flex items-center gap-2 py-0.5 text-sm ${final && !won ? "text-mist" : ""}`}>
          <span className="w-4 text-right text-xs tabular-nums text-mist">{seedOf.get(team.id)}</span>
          <TeamCrest team={team} size={18} />
          <span className={`flex-1 truncate ${won ? "font-semibold" : ""}`}>{team.nickname}</span>
          {final && <span className="stat-number">{score}</span>}
        </div>
      ))}
      <div className="mt-1 text-right text-[10px] uppercase tracking-wider text-mist">
        {final ? (game.overtime ? "Final/OT" : "Final") : game.neutral_site ? "Neutral site" : "Upcoming"}
      </div>
    </Link>
  );
}
