import Link from "next/link";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { RatingBar } from "@/components/ui/RatingBar";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatAttribute, formatHeight, formatMoney, injuryDetail } from "@/lib/format";
import { groupsFor } from "@/lib/stats";
import type { CareerOut, PlayerDetail, PlayerSeasonStats } from "@/lib/types";

export function PlayerView({ player, stats, career }: {
  player: PlayerDetail; stats: PlayerSeasonStats; career?: CareerOut;
}) {
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
              : <>{player.years_pro ? `${player.years_pro} yr pro` : "Rookie"} · {injuryDetail(player)}</>}
            {player.contract && <> · {formatMoney(player.contract.salary)}/yr through {player.contract.end_year}</>}
            {player.draft_pick
              ? <> · Drafted {player.draft_year}, round {player.draft_round}, pick {player.draft_pick}</>
              : player.draft_year && <> · Undrafted ({player.draft_year})</>}
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

      {career && (career.seasons.length > 0 || career.awards.length > 0) && <Career career={career} />}

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

function Career({ career }: { career: CareerOut }) {
  // Season totals only ("LONG" columns are per-game maximums).
  const groups = groupsFor(career.totals).map((g) => ({
    ...g, columns: g.columns.filter(([label]) => label !== "LONG"),
  }));
  return (
    <section className="panel overflow-x-auto" aria-label="Career">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4">
        <h2 className="eyebrow mr-2">Career · {career.games} games</h2>
        {career.awards.map((a) => (
          <span key={`${a.award}-${a.year}`} title={a.summary}
            className="rounded bg-gold/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-gold">
            {a.year} {a.label}
          </span>
        ))}
      </div>
      {career.seasons.length > 0 && (
        <table className="mt-2 w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-white/5 text-[11px] uppercase tracking-wider text-mist">
              <th className="px-4 py-2 text-left font-medium">Year</th>
              <th className="px-4 py-2 text-left font-medium">Team</th>
              <th className="px-3 py-2 text-right font-medium">G</th>
              {groups.flatMap((g) => g.columns.map(([label]) => (
                <th key={`${g.title}-${label}`} className="px-3 py-2 text-right font-medium" title={g.title}>{label}</th>
              )))}
            </tr>
          </thead>
          <tbody>
            {career.seasons.map((s) => (
              <tr key={s.year} className="border-b border-white/[0.03]">
                <td className="px-4 py-2 tabular-nums">{s.year}</td>
                <td className="px-4 py-2">{s.team.abbreviation}</td>
                <td className="px-3 py-2 text-right tabular-nums">{s.games}</td>
                {groups.flatMap((g) => g.columns.map(([label, value]) => (
                  <td key={`${g.title}-${label}`} className="px-3 py-2 text-right tabular-nums">{value(s.stats)}</td>
                )))}
              </tr>
            ))}
            {career.seasons.length > 1 && (
              <tr className="font-semibold">
                <td className="px-4 py-2" colSpan={2}>Career</td>
                <td className="px-3 py-2 text-right tabular-nums">{career.games}</td>
                {groups.flatMap((g) => g.columns.map(([label, value]) => (
                  <td key={`${g.title}-${label}`} className="px-3 py-2 text-right tabular-nums">{value(career.totals)}</td>
                )))}
              </tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}
