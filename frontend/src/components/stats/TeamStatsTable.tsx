"use client";

import { useMemo, useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatRecord } from "@/lib/format";
import type { TeamSeasonRow } from "@/lib/types";

type Column = {
  key: string;
  label: string;
  title: string;
  value: (r: TeamSeasonRow) => number;
  perGame?: boolean; // show with one decimal
  low?: boolean; // smaller is better, so the first click sorts ascending
};

const per = (total: (r: TeamSeasonRow) => number) => (r: TeamSeasonRow) => (r.games ? total(r) / r.games : 0);

export const COLUMNS: Column[] = [
  { key: "ppg", perGame: true, label: "PF/G", title: "Points per game", value: per((r) => r.points_for) },
  { key: "oppg", perGame: true, label: "PA/G", title: "Points allowed per game", value: per((r) => r.points_against), low: true },
  { key: "ypg", perGame: true, label: "YDS/G", title: "Yards per game", value: per((r) => r.total_yds) },
  { key: "pypg", perGame: true, label: "PASS/G", title: "Passing yards per game", value: per((r) => r.pass_yds) },
  { key: "rypg", perGame: true, label: "RUSH/G", title: "Rushing yards per game", value: per((r) => r.rush_yds) },
  { key: "aypg", perGame: true, label: "ALLOW/G", title: "Yards allowed per game", value: per((r) => r.yds_allowed), low: true },
  { key: "to", label: "TO", title: "Turnovers (giveaways)", value: (r) => r.turnovers, low: true },
  { key: "tk", label: "TAKE", title: "Takeaways", value: (r) => r.takeaways },
  { key: "sk", label: "SACK", title: "Sacks by the defense", value: (r) => r.sacks },
];

export function TeamStatsTable({ rows, teamId }: { rows: TeamSeasonRow[]; teamId: number }) {
  const [sort, setSort] = useState<{ key: string; asc: boolean }>({ key: "ppg", asc: false });
  const sorted = useMemo(() => {
    const column = COLUMNS.find((c) => c.key === sort.key)!;
    return [...rows].sort((a, b) => (column.value(a) - column.value(b)) * (sort.asc ? 1 : -1)
      || a.team.full_name.localeCompare(b.team.full_name));
  }, [rows, sort]);

  function toggle(column: Column) {
    setSort((s) => (s.key === column.key ? { key: s.key, asc: !s.asc } : { key: column.key, asc: !!column.low }));
  }

  return (
    <section className="panel overflow-x-auto" aria-label="Team stats">
      <table className="w-full min-w-[820px] text-sm">
        <thead>
          <tr className="border-b border-white/5 text-[11px] uppercase tracking-wider text-mist">
            <th className="px-3 py-3 text-left font-medium">#</th>
            <th className="px-3 py-3 text-left font-medium">Team</th>
            <th className="px-3 py-3 text-right font-medium">W-L</th>
            {COLUMNS.map((c) => (
              <th key={c.key} className="px-3 py-3 text-right font-medium" title={c.title}
                aria-sort={sort.key === c.key ? (sort.asc ? "ascending" : "descending") : undefined}>
                <button type="button" onClick={() => toggle(c)}
                  className={`uppercase hover:text-chalk ${sort.key === c.key ? "text-gold" : ""}`}>
                  {c.label}{sort.key === c.key && <span aria-hidden> {sort.asc ? "▲" : "▼"}</span>}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={row.team.id} className={`border-b border-white/[0.03] ${row.team.id === teamId ? "bg-gold/[0.07]" : ""}`}>
              <td className="stat-number px-3 py-2 text-mist">{i + 1}</td>
              <td className="px-3 py-2">
                <span className="flex items-center gap-2"><TeamCrest team={row.team} size={20} />{row.team.full_name}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{formatRecord(row)}</td>
              {COLUMNS.map((c) => (
                <td key={c.key} className="px-3 py-2 text-right tabular-nums">
                  {c.perGame ? (row.games ? c.value(row).toFixed(1) : "–") : c.value(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
