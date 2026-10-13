import Link from "next/link";
import { PlayerName } from "@/components/ui/PlayerName";
import { GAME, type Site } from "@/lib/site";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { Panel } from "@/components/ui/Panel";
import { callLabel, formatPossession } from "@/lib/games";
import { hasGroup, snapShares, STAT_GROUPS } from "@/lib/stats";
import { injuryDuration } from "@/lib/format";
import { POSITIONS, type GameDetail, type PlayerGameLine, type PlayOut, type Position, type TeamSummary } from "@/lib/types";

type Side = "home" | "away";

const PERIOD_LABELS = ["1", "2", "3", "4"];

export function GameView({ detail, site = GAME }: { detail: GameDetail; site?: Site }) {
  const base = site.base;
  const { game } = detail;
  const final = game.status === "final";
  const teams: Record<Side, TeamSummary> = { home: game.home, away: game.away };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {game.stage === "playoff" ? (
          <Link href={`${base}/playoffs`} className="text-sm text-gold hover:underline">← Playoff bracket</Link>
        ) : (
          <Link href={`${base}/schedule?week=${game.week}`} className="text-sm text-gold hover:underline">
            ← Week {game.week} schedule
          </Link>
        )}
        <h1 className="eyebrow">
          <span className="sr-only">{game.away.full_name} at {game.home.full_name}, </span>
          {detail.season_year} · {game.round_name ?? `Week ${game.week}`}
          {game.neutral_site && " · Neutral site"}
        </h1>
      </div>

      <section className="panel grid grid-cols-[1fr_auto_1fr] items-center gap-4 p-6" aria-label="Scoreboard">
        <Scoreboard team={game.away} score={game.away_score} won={final && game.away_score! > game.home_score!} label="Away" />
        <div className="text-center">
          <div className="font-display text-sm font-semibold uppercase tracking-widest text-mist">
            {final ? (game.overtime ? "Final / OT" : "Final") : "Not played yet"}
          </div>
          <div className="text-xs text-mist">@</div>
        </div>
        <Scoreboard team={game.home} score={game.home_score} won={final && game.home_score! > game.away_score!} label="Home" alignRight />
      </section>

      {!final ? (
        <p className="panel p-6 text-center text-sm text-mist">
          This game hasn&apos;t been played yet.{" "}
          {site.shared ? "Its box score shows up here once it is." : "Sim the week from the Schedule or Dashboard to see the box score."}
        </p>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Line score">
              <LineScore detail={detail} teams={teams} />
            </Panel>
            <Panel title="Team stats">
              <TeamStats detail={detail} teams={teams} />
            </Panel>
          </div>
          <Panel title="Scoring summary">
            <PlayList plays={detail.scoring_plays} teams={teams} />
          </Panel>
          <div className="grid gap-6 lg:grid-cols-2">
            {(["away", "home"] as const).map((side) => (
              <BoxScore key={side} team={teams[side]} site={site}
                players={detail.players.filter((p) => p.team_id === teams[side].id)} />
            ))}
          </div>
          {detail.injuries && detail.injuries.length > 0 && (
            <Panel title="Injuries">
              <ul className="space-y-1.5" aria-label="Injuries">
                {detail.injuries.map((injury) => {
                  const team = injury.team_id === teams.home.id ? teams.home : teams.away;
                  return (
                    <li key={`${injury.player_id}-${injury.quarter}-${injury.clock}`}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                      <span className="w-14 text-xs tabular-nums text-mist">
                        {injury.quarter > 4 ? "OT" : `Q${injury.quarter}`} {injury.clock}
                      </span>
                      <span className="w-10 text-xs font-semibold text-mist">{team.abbreviation}</span>
                      <PlayerName id={injury.player_id} site={site} className="hover:text-gold">
                        <span className="mr-1.5 text-xs text-mist">{injury.position}</span>
                        {injury.name}
                      </PlayerName>
                      <span className="text-mist">{injury.injury}</span>
                      <span className="text-xs text-rose-300">{injuryDuration(injury.weeks)}</span>
                    </li>
                  );
                })}
              </ul>
            </Panel>
          )}
          {detail.log_compacted ? (
            <Panel title="Play-by-play">
              <p className="mb-3 text-sm text-mist">
                Full play-by-play is kept for the last two seasons, and for your games and the
                playoffs before that. This game keeps its scoring plays and injuries.
              </p>
              <PlayByPlay gameId={game.id} plays={detail.plays} teams={teams} base={base} />
            </Panel>
          ) : (
            <Panel title="Play-by-play" action={
              <div className="flex gap-2">
                <Link href={`${base}/games/${game.id}/watch?highlights=1&auto=1`} className="btn btn-ghost px-3 py-1 text-xs">
                  Highlights
                </Link>
                <Link href={`${base}/games/${game.id}/watch?auto=1`} className="btn btn-primary px-3 py-1 text-xs">
                  Watch in 3D
                </Link>
              </div>
            }>
              <PlayByPlay gameId={game.id} plays={detail.plays} teams={teams} base={base} />
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function Scoreboard({ team, score, won, label, alignRight = false }: {
  team: TeamSummary; score: number | null; won: boolean; label: string; alignRight?: boolean;
}) {
  return (
    <div className={`flex items-center gap-4 ${alignRight ? "flex-row-reverse text-right" : ""}`}>
      <TeamCrest team={team} size={56} />
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-wider text-mist">{label}</div>
        <div className="truncate font-display text-xl font-bold uppercase sm:text-2xl">{team.full_name}</div>
      </div>
      {score !== null && (
        <div className={`stat-number text-5xl ${won ? "" : "text-mist"} ${alignRight ? "mr-auto" : "ml-auto"}`}
          data-testid={`score-${label.toLowerCase()}`}>
          {score}
        </div>
      )}
    </div>
  );
}

function LineScore({ detail, teams }: { detail: GameDetail; teams: Record<Side, TeamSummary> }) {
  const periods = detail.line_score.home.length;
  const labels = Array.from({ length: periods }, (_, i) => PERIOD_LABELS[i] ?? (periods > 5 ? `OT${i - 3}` : "OT"));
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[11px] uppercase tracking-wider text-mist">
          <th className="pb-2 text-left font-medium">Team</th>
          {labels.map((l) => <th key={l} className="pb-2 text-center font-medium">{l}</th>)}
          <th className="pb-2 text-right font-medium">T</th>
        </tr>
      </thead>
      <tbody>
        {(["away", "home"] as const).map((side) => (
          <tr key={side} className="border-t border-white/5">
            <td className="py-2 font-medium">{teams[side].abbreviation}</td>
            {detail.line_score[side].map((points, i) => (
              <td key={i} className="py-2 text-center tabular-nums">{points}</td>
            ))}
            <td className="stat-number py-2 text-right text-base">
              {detail.line_score[side].reduce((a, b) => a + b, 0)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const TEAM_ROWS: [string, (s: Record<string, number>) => string][] = [
  ["Total yards", (s) => String(s.total_yds)],
  ["Passing", (s) => `${s.pass_yds} (${s.pass_cmp}/${s.pass_att})`],
  ["Rushing", (s) => `${s.rush_yds} (${s.rush_att} att)`],
  ["First downs", (s) => String(s.first_downs)],
  ["3rd down", (s) => `${s.third_down_conv}/${s.third_down_att}`],
  ["Turnovers", (s) => String(s.turnovers)],
  ["Sacks allowed", (s) => String(s.sacks_allowed)],
  ["Penalties", (s) => `${s.penalties}-${s.penalty_yds}`],
  ["Possession", (s) => formatPossession(s.time_of_possession)],
];

function TeamStats({ detail, teams }: { detail: GameDetail; teams: Record<Side, TeamSummary> }) {
  const away = detail.team_stats.away ?? {};
  const home = detail.team_stats.home ?? {};
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[11px] uppercase tracking-wider text-mist">
          <th className="pb-2 text-left font-medium">{teams.away.abbreviation}</th>
          <th className="pb-2 font-medium" />
          <th className="pb-2 text-right font-medium">{teams.home.abbreviation}</th>
        </tr>
      </thead>
      <tbody>
        {TEAM_ROWS.map(([label, fmt]) => (
          <tr key={label} className="border-t border-white/5">
            <td className="py-1.5 tabular-nums">{fmt(away)}</td>
            <td className="py-1.5 text-center text-xs text-mist">{label}</td>
            <td className="py-1.5 text-right tabular-nums">{fmt(home)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BoxScore({ team, players, site }: { team: TeamSummary; players: PlayerGameLine[]; site: Site }) {
  return (
    <section className="panel space-y-4 p-5" aria-label={`${team.full_name} box score`}>
      <h2 className="flex items-center gap-2 font-display text-xl font-bold uppercase">
        <TeamCrest team={team} size={24} /> {team.nickname}
      </h2>
      {STAT_GROUPS.filter((section) => !section.ownSection).map((section) => {
        const rows = players
          .filter((p) => hasGroup(section, p.stats))
          .sort((a, b) => (b.stats[section.sortBy] ?? 0) - (a.stats[section.sortBy] ?? 0))
          .slice(0, section.title === "Defense" ? 6 : 5);
        if (!rows.length) return null;
        return (
          <div key={section.title} className="overflow-x-auto">
            <table className="w-full text-sm" aria-label={`${team.abbreviation} ${section.title.toLowerCase()}`}>
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-mist">
                  <th className="pb-1 text-left font-medium">{section.title}</th>
                  {section.columns.map(([label]) => (
                    <th key={label} className="pb-1 text-right font-medium">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.player_id} className="border-t border-white/5">
                    <td className="py-1 pr-2">
                      <PlayerName id={p.player_id} site={site} className="hover:text-gold">{p.name}</PlayerName>{" "}
                      <span className="text-xs text-mist">{p.position}</span>
                    </td>
                    {section.columns.map(([label, fmt]) => (
                      <td key={label} className="py-1 text-right tabular-nums">{fmt(p.stats)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
      <SnapCounts team={team} players={players} site={site} />
    </section>
  );
}

/** Everyone who played, by position, with his share of his unit's snaps. */
function SnapCounts({ team, players, site }: { team: TeamSummary; players: PlayerGameLine[]; site: Site }) {
  const rows = snapShares(players).sort((a, b) =>
    POSITIONS.indexOf(a.position as Position) - POSITIONS.indexOf(b.position as Position)
    || b.snaps - a.snaps);
  if (!rows.length) return null; // (games played before snap counts)
  return (
    <details className="rounded-lg border border-white/5">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-mist">
        Snap counts
      </summary>
      <table className="w-full text-sm" aria-label={`${team.abbreviation} snap counts`}>
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-mist">
            <th className="px-3 pb-1 text-left font-medium">Player</th>
            <th className="pb-1 text-right font-medium">Snaps</th>
            <th className="px-3 pb-1 text-right font-medium">Share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.player_id} className="border-t border-white/5">
              <td className="px-3 py-1">
                <PlayerName id={p.player_id} site={site} className="hover:text-gold">{p.name}</PlayerName>{" "}
                <span className="text-xs text-mist">{p.position}</span>
              </td>
              <td className="py-1 text-right tabular-nums">{p.snaps}</td>
              <td className="px-3 py-1 text-right tabular-nums">{Math.round(p.share * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function quarterName(q: number): string {
  return q <= 4 ? `Quarter ${q}` : q === 5 ? "Overtime" : `Overtime ${q - 4}`;
}

function PlayList({ plays, teams }: { plays: PlayOut[]; teams: Record<Side, TeamSummary> }) {
  if (!plays.length) return <p className="text-sm text-mist">No scoring.</p>;
  return (
    <ol className="space-y-2">
      {plays.map((play) => (
        <li key={play.n} className="grid grid-cols-[4.5rem_3rem_minmax(0,1fr)_4.5rem] items-baseline gap-3 text-sm">
          <span className="text-xs text-mist">{play.quarter <= 4 ? `Q${play.quarter}` : "OT"} {play.clock}</span>
          <span className="font-display font-semibold">{play.offense}</span>
          <span>{play.text}</span>
          <span className="stat-number text-right">
            {play.away_score}-{play.home_score}
          </span>
        </li>
      ))}
      <li className="text-right text-[11px] uppercase tracking-wider text-mist">
        {teams.away.abbreviation}-{teams.home.abbreviation}
      </li>
    </ol>
  );
}

function PlayByPlay({ gameId, plays, teams, base }: {
  gameId: number; plays: PlayOut[]; teams: Record<Side, TeamSummary>; base: string;
}) {
  const quarters = [...new Set(plays.map((p) => p.quarter))];
  return (
    <div className="space-y-3">
      {quarters.map((q) => (
        <details key={q} open={q === 1} className="rounded-lg border border-white/5">
          <summary className="cursor-pointer px-4 py-2 font-display font-semibold uppercase tracking-wide">
            {quarterName(q)}
          </summary>
          <ol className="divide-y divide-white/[0.04]" aria-label={quarterName(q)}>
            {plays.filter((p) => p.quarter === q).map((play) => (
              <li key={play.n} className={`grid grid-cols-[3.5rem_7rem_minmax(0,1fr)_auto] gap-3 px-4 py-2 text-sm ${play.scoring ? "bg-gold/[0.05]" : ""}`}>
                <span className="text-xs tabular-nums text-mist">{play.clock}</span>
                <span className="text-xs text-mist">
                  {play.down ? `${play.offense} ${ordinal(play.down)}&${play.distance}` : play.offense}
                  {play.spot && <span className="block">at {play.spot}</span>}
                </span>
                <span>
                  {play.text}
                  {callLabel(play.play_name, play.defense_name) && (
                    <span className="block text-xs text-mist">{callLabel(play.play_name, play.defense_name)}</span>
                  )}
                </span>
                <Link href={`${base}/games/${gameId}/watch?play=${play.n}`} aria-label={`Watch play ${play.n}`}
                  className="self-start text-xs font-semibold text-gold hover:underline">
                  Watch
                </Link>
              </li>
            ))}
          </ol>
        </details>
      ))}
      <p className="text-xs text-mist">
        {teams.away.full_name} at {teams.home.full_name} · {plays.length} plays
      </p>
    </div>
  );
}

function ordinal(n: number): string {
  return ["", "1st", "2nd", "3rd", "4th"][n] ?? `${n}th`;
}
