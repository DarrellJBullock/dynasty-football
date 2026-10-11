import Link from "next/link";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { RatingBar } from "@/components/ui/RatingBar";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatAttribute, formatHeight, formatMoney, injuryLabel } from "@/lib/format";
import { groupsFor } from "@/lib/stats";
import type { PlayerDetail, PlayerSeasonStats } from "@/lib/types";

export function PlayerView({ player, stats }: { player: PlayerDetail; stats: PlayerSeasonStats }) {
  const groups = groupsFor(stats.totals);
  const team = stats.team;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="panel flex flex-wrap items-center gap-6 p-6" aria-label="Player">
        {team && <TeamCrest team={team} size={64} />}
        <div className="min-w-0 flex-1">
          <div className="eyebrow text-gold">
            {player.position} · #{player.jersey_number} · {team ? team.full_name : "Free agent"}
          </div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">{player.full_name}</h1>
          <p className="mt-1 text-sm text-mist">
            Age {player.age} · {formatHeight(player.height_in)}, {player.weight_lb} lb · {player.college} ·{" "}
            {player.retired_year
              ? `Retired after ${player.retired_year}`
              : <>{player.years_pro ? `${player.years_pro} yr pro` : "Rookie"} · {injuryLabel(player.injury_status)}</>}
            {player.contract && <> · {formatMoney(player.contract.salary)}/yr through {player.contract.end_year}</>}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-center">
            <div className="eyebrow">OVR</div>
            <OvrBadge value={player.overall} size="lg" />
          </div>
          <div className="text-center">
            <div className="eyebrow">POT</div>
            <div className="stat-number mt-1 text-3xl text-mist">{player.potential}</div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="panel space-y-4 p-5" aria-label="Season totals">
          <h2 className="eyebrow">{stats.season.year} season · {stats.games} game{stats.games === 1 ? "" : "s"}</h2>
          {groups.length === 0 ? (
            <p className="text-sm text-mist">No stats yet this season.</p>
          ) : (
            groups.map((group) => (
              <dl key={group.title} className="grid grid-cols-[6rem_repeat(5,minmax(0,1fr))] items-center gap-2 text-sm">
                <dt className="eyebrow">{group.title}</dt>
                {group.columns.map(([label, value]) => (
                  <div key={label} className="text-center">
                    <div className="text-[10px] uppercase tracking-wider text-mist">{label}</div>
                    <dd className="stat-number text-xl">{value(stats.totals)}</dd>
                  </div>
                ))}
              </dl>
            ))
          )}
        </section>
        <section className="panel space-y-2.5 p-5" aria-label="Key ratings">
          <h2 className="eyebrow">Key ratings</h2>
          {Object.entries(player.key_ratings).map(([name, value]) => (
            <RatingBar key={name} label={formatAttribute(name)} value={value} emphasis />
          ))}
        </section>
      </div>

      <section className="panel overflow-x-auto" aria-label="Game log">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-white/5 text-[11px] uppercase tracking-wider text-mist">
              <th className="px-4 py-3 text-left font-medium">Wk</th>
              <th className="px-4 py-3 text-left font-medium">Opponent</th>
              <th className="px-4 py-3 text-left font-medium">Result</th>
              {groups.flatMap((g) => g.columns.map(([label]) => (
                <th key={`${g.title}-${label}`} className="px-3 py-3 text-right font-medium" title={g.title}>{label}</th>
              )))}
            </tr>
          </thead>
          <tbody>
            {stats.game_log.map((game) => (
              <tr key={game.game_id} className="border-b border-white/[0.03]">
                <td className="px-4 py-2 tabular-nums text-mist">{game.week}</td>
                <td className="px-4 py-2">
                  <span className="flex items-center gap-2">
                    <span className="w-3 text-xs text-mist">{game.home ? "vs" : "@"}</span>
                    <TeamCrest team={game.opponent} size={18} />
                    {game.opponent.abbreviation}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <Link href={`/games/${game.game_id}`} className="hover:text-gold">{game.result}</Link>
                </td>
                {groups.flatMap((g) => g.columns.map(([label, value]) => (
                  <td key={`${g.title}-${label}`} className="px-3 py-2 text-right tabular-nums">{value(game.stats)}</td>
                )))}
              </tr>
            ))}
            {stats.game_log.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-10 text-center text-mist">No games played yet.</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
