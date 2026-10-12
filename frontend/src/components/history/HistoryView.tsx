"use client";

import Link from "next/link";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import type { HistoryOut, RecordRow, SeasonHistory, TeamSummary } from "@/lib/types";

export function HistoryView({ history, team, league }: {
  history: HistoryOut; team: TeamSummary; league: string;
}) {
  const [view, setView] = useState<"single_season" | "career">("single_season");
  const titles = history.seasons.filter((s) => s.champion?.id === team.id).length;
  // The last ten finished seasons (a report covers up to ten).
  const finished = history.seasons.filter((s) => s.complete).map((s) => s.year);
  const report = finished.length
    ? { from: Math.max(Math.min(...finished), Math.max(...finished) - 9), to: Math.max(...finished) }
    : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <div className="eyebrow text-gold">{league}</div>
        <h1 className="font-display text-4xl font-bold uppercase tracking-wide">History</h1>
        <p className="mt-1 text-sm text-mist">
          {history.seasons.length} season{history.seasons.length === 1 ? "" : "s"} ·{" "}
          {titles} {team.nickname} championship{titles === 1 ? "" : "s"}
          {report && (
            <>
              {" · "}
              <Link href={`/dynasty?from=${report.from}&to=${report.to}`} className="text-gold hover:underline">
                Dynasty report, {report.from}–{report.to} →
              </Link>
            </>
          )}
        </p>
      </div>

      <section className="space-y-4" aria-label="Seasons">
        {history.seasons.map((season) => <SeasonCard key={season.season_id} season={season} team={team} />)}
      </section>

      <section className="panel p-5" aria-label="Records">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="eyebrow">Records · regular season</h2>
          <div className="flex gap-1" role="tablist" aria-label="Record type">
            {(["single_season", "career"] as const).map((key) => (
              <button key={key} type="button" role="tab" aria-selected={view === key}
                className={`rounded-md px-3 py-1 text-xs font-semibold uppercase ${
                  view === key ? "bg-gold text-ink-950" : "text-mist hover:bg-white/5"}`}
                onClick={() => setView(key)}>
                {key === "career" ? "Career" : "Single season"}
              </button>
            ))}
          </div>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {history.records.map((category) => (
            <div key={category.key} role="group" aria-label={category.label}>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-mist">{category.label}</h3>
              {category[view].length === 0 ? (
                <p className="text-sm text-mist">No games played yet.</p>
              ) : (
                <ol className="space-y-1">
                  {category[view].map((row, i) => <RecordLine key={`${row.player_id}-${row.year}`} row={row} rank={i + 1} />)}
                </ol>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/** One season: its champion, awards, and how the franchise did. */
export function SeasonCard({ season, team }: { season: SeasonHistory; team: TeamSummary }) {
  const record = season.franchise_record;
  const won = season.champion?.id === team.id;
  return (
    <article className={`panel p-5 ${won ? "ring-1 ring-gold/50" : ""}`} aria-label={`${season.year} season`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="font-display text-3xl font-bold tabular-nums">{season.year}</div>
          {season.champion ? (
            <div className="flex items-center gap-2">
              <TeamCrest team={season.champion} size={36} />
              <div>
                <div className="eyebrow text-gold">Champion</div>
                <div className="font-semibold">{season.champion.full_name}</div>
                {season.runner_up && <div className="text-xs text-mist">over {season.runner_up.full_name}</div>}
              </div>
            </div>
          ) : (
            <span className="text-sm text-mist">{season.phase === "regular_season" || season.phase === "playoffs"
              ? "In progress" : "Not finished"}</span>
          )}
        </div>
        {record && (
          <div className="text-right text-sm" aria-label="Your season">
            <div className="eyebrow">{team.nickname}</div>
            <div className="stat-number text-xl">
              {record.wins}-{record.losses}{record.ties ? `-${record.ties}` : ""}
            </div>
            <div className={won ? "text-gold" : "text-mist"}>{season.franchise_result}</div>
          </div>
        )}
      </div>
      {season.awards.length > 0 && (
        <ul className="mt-4 grid gap-2 border-t border-white/5 pt-3 sm:grid-cols-2 lg:grid-cols-3" aria-label={`${season.year} awards`}>
          {season.awards.map((a) => (
            <li key={a.award} className="text-sm">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-gold">{a.label}</div>
              <Link href={`/players/${a.player_id}`} className="hover:text-gold">
                <span className="mr-1.5 text-xs text-mist">{a.position}</span>
                {a.name}
              </Link>
              {a.team && <span className="ml-1.5 text-xs text-mist">{a.team.abbreviation}</span>}
              <div className="text-xs text-mist">{a.summary}</div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function RecordLine({ row, rank }: { row: RecordRow; rank: number }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className="w-4 text-xs tabular-nums text-mist">{rank}</span>
      <Link href={`/players/${row.player_id}`} className="min-w-0 flex-1 truncate hover:text-gold">
        <span className="mr-1.5 text-xs text-mist">{row.position}</span>
        {row.name}
        {row.retired && <span className="ml-1 text-[10px] uppercase text-mist">ret.</span>}
      </Link>
      <span className="text-xs text-mist">{row.year ?? `${row.games} G`}</span>
      <span className="w-14 text-right font-semibold tabular-nums">{row.value.toLocaleString()}</span>
    </li>
  );
}
