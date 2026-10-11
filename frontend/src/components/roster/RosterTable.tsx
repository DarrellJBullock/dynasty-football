"use client";

import { OvrBadge } from "@/components/ui/OvrBadge";
import { ATTRIBUTE_ABBREVIATIONS } from "@/lib/attributes";
import { formatHeight, formatMoney, injuryDetail, injuryLabel, yearsRemaining } from "@/lib/format";
import type { SortKey, SortState } from "@/lib/roster";
import type { PlayerSummary } from "@/lib/types";

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: "jersey_number", label: "#", className: "w-10" },
  { key: "last_name", label: "Player" },
  { key: "position", label: "Pos", className: "w-14" },
  { key: "overall", label: "OVR", className: "w-14 text-center" },
  { key: "potential", label: "POT", className: "w-14 text-center" },
  { key: "age", label: "Age", className: "w-12 text-right" },
  { key: null, label: "Ht / Wt", className: "hidden md:table-cell w-24 text-right" },
  { key: null, label: "Key ratings", className: "hidden xl:table-cell" },
  { key: "salary", label: "Contract", className: "hidden sm:table-cell w-28 text-right" },
];

export function RosterTable({
  players,
  sort,
  onSort,
  selectedId,
  onSelect,
  seasonYear,
}: {
  players: PlayerSummary[];
  sort: SortState;
  onSort: (key: SortKey) => void;
  selectedId: number | null;
  onSelect: (playerId: number) => void;
  seasonYear: number;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b border-white/5 text-left text-[11px] uppercase tracking-wider text-mist">
            {COLUMNS.map((col) => (
              <th
                key={col.label}
                scope="col"
                className={`px-3 py-3 font-medium ${col.className ?? ""}`}
                aria-sort={
                  col.key && sort.key === col.key
                    ? sort.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                {col.key ? (
                  <button
                    type="button"
                    onClick={() => onSort(col.key!)}
                    className={`inline-flex items-center gap-1 uppercase hover:text-chalk ${
                      sort.key === col.key ? "text-gold" : ""
                    }`}
                  >
                    {col.label}
                    {sort.key === col.key && (
                      <span aria-hidden>{sort.direction === "asc" ? "▲" : "▼"}</span>
                    )}
                  </button>
                ) : (
                  col.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr
              key={player.id}
              onClick={() => onSelect(player.id)}
              className={`cursor-pointer border-b border-white/[0.03] transition-colors ${
                player.id === selectedId ? "bg-gold/[0.07]" : "hover:bg-white/[0.03]"
              }`}
            >
              <td className="stat-number px-3 py-2.5 text-base text-mist">{player.jersey_number}</td>
              <td className="px-3 py-2.5">
                <button
                  type="button"
                  className="text-left font-medium hover:text-gold"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(player.id);
                  }}
                >
                  {player.full_name}
                </button>
                <div className="flex items-center gap-2 text-xs text-mist">
                  <span>{player.college}</span>
                  {player.injury_status !== "healthy" && (
                    <span title={injuryDetail(player)}
                      className="rounded bg-rose-500/15 px-1.5 text-[10px] font-semibold uppercase text-rose-300">
                      {injuryLabel(player.injury_status)}
                    </span>
                  )}
                  {player.development_trait !== "normal" && (
                    <span className="rounded bg-amber-400/10 px-1.5 text-[10px] font-semibold uppercase text-amber-300">
                      {player.development_trait}
                    </span>
                  )}
                </div>
              </td>
              <td className="px-3 py-2.5 font-display font-semibold">{player.position}</td>
              <td className="px-3 py-2.5 text-center">
                <OvrBadge value={player.overall} />
              </td>
              <td className="px-3 py-2.5 text-center text-mist tabular-nums">{player.potential}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{player.age}</td>
              <td className="hidden px-3 py-2.5 text-right text-mist tabular-nums md:table-cell">
                {formatHeight(player.height_in)} / {player.weight_lb}
              </td>
              <td className="hidden px-3 py-2.5 xl:table-cell">
                <div className="flex gap-1.5">
                  {Object.entries(player.key_ratings)
                    .slice(0, 3)
                    .map(([name, value]) => (
                      <span
                        key={name}
                        className="rounded bg-white/[0.04] px-1.5 py-0.5 text-[11px] tabular-nums text-mist"
                      >
                        {ATTRIBUTE_ABBREVIATIONS[name] ?? name}{" "}
                        <span className="text-chalk">{value}</span>
                      </span>
                    ))}
                </div>
              </td>
              <td className="hidden px-3 py-2.5 text-right sm:table-cell">
                {player.contract ? (
                  <>
                    <div className="tabular-nums">{formatMoney(player.contract.salary)}</div>
                    <div className="text-xs text-mist">
                      {yearsRemaining(player.contract.end_year, seasonYear)} yr
                    </div>
                  </>
                ) : (
                  <span className="text-mist">—</span>
                )}
              </td>
            </tr>
          ))}
          {players.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length} className="px-3 py-12 text-center text-sm text-mist">
                No players match these filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
