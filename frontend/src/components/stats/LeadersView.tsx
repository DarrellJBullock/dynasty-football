import Link from "next/link";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { STAT_LABELS } from "@/lib/stats";
import type { LeaderCategory, LeaderRow } from "@/lib/types";

function PlayerLink({ row }: { row: LeaderRow }) {
  return (
    <Link href={`/players/${row.player_id}`} className="font-medium hover:text-gold">
      {row.name}
    </Link>
  );
}

/** Grid of categories, top few in each. */
export function LeaderCards({ categories, teamId }: { categories: LeaderCategory[]; teamId: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {categories.map((category) => (
        <section key={category.key} className="panel p-4" aria-label={category.label}>
          <header className="mb-3 flex items-center justify-between">
            <h2 className="eyebrow">{category.label}</h2>
            <Link href={`/stats?category=${category.key}`} className="text-xs text-gold hover:underline">
              Top 25 →
            </Link>
          </header>
          {category.leaders.length === 0 ? (
            <p className="text-sm text-mist">No games played yet.</p>
          ) : (
            <ol className="space-y-1.5">
              {category.leaders.map((row, i) => (
                <li key={row.player_id}
                  className={`grid grid-cols-[1rem_auto_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-1.5 py-1 text-sm ${
                    row.team?.id === teamId ? "bg-gold/[0.07]" : ""}`}>
                  <span className="stat-number text-mist">{i + 1}</span>
                  {row.team ? <TeamCrest team={row.team} size={18} /> : <span />}
                  <span className="min-w-0 truncate">
                    <PlayerLink row={row} /> <span className="text-xs text-mist">{row.position}</span>
                  </span>
                  <span className="stat-number text-base">{row.value}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      ))}
    </div>
  );
}

/** One category in full. */
export function LeaderTable({ category, teamId }: { category: LeaderCategory; teamId: number }) {
  const columns = category.leaders[0] ? Object.keys(category.leaders[0].stats) : [];
  return (
    <section className="panel overflow-x-auto" aria-label={`${category.label} leaders`}>
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b border-white/5 text-left text-[11px] uppercase tracking-wider text-mist">
            <th className="px-4 py-3 font-medium">#</th>
            <th className="px-4 py-3 font-medium">Player</th>
            <th className="px-4 py-3 font-medium">Team</th>
            <th className="px-4 py-3 text-right font-medium">G</th>
            <th className="px-4 py-3 text-right font-medium text-gold">{category.label}</th>
            {columns.map((c) => <th key={c} className="px-4 py-3 text-right font-medium">{STAT_LABELS[c] ?? c}</th>)}
          </tr>
        </thead>
        <tbody>
          {category.leaders.map((row, i) => (
            <tr key={row.player_id} className={`border-b border-white/[0.03] ${row.team?.id === teamId ? "bg-gold/[0.07]" : ""}`}>
              <td className="stat-number px-4 py-2 text-mist">{i + 1}</td>
              <td className="px-4 py-2"><PlayerLink row={row} /> <span className="text-xs text-mist">{row.position}</span></td>
              <td className="px-4 py-2">
                {row.team && <span className="flex items-center gap-2"><TeamCrest team={row.team} size={18} />{row.team.abbreviation}</span>}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">{row.games}</td>
              <td className="stat-number px-4 py-2 text-right text-base">{row.value}</td>
              {columns.map((c) => <td key={c} className="px-4 py-2 text-right tabular-nums">{row.stats[c]}</td>)}
            </tr>
          ))}
          {category.leaders.length === 0 && (
            <tr><td colSpan={5 + columns.length} className="px-4 py-10 text-center text-mist">No games played yet.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
