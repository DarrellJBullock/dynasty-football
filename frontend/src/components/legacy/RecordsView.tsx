"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { RecordLine } from "@/components/history/HistoryView";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { RecordRow, TeamRecords, TeamSummary } from "@/lib/types";

type View = "single_game" | "single_season" | "career";
const VIEWS: [View, string][] = [["single_game", "Single game"], ["single_season", "Single season"], ["career", "Career"]];

/**
 * A team's record book: its records (games for this team), its Hall of Famers and retired
 * numbers, and, for whoever runs the team, former players whose numbers it could retire.
 */
export function RecordsView({ initial, teams }: { initial: TeamRecords; teams: TeamSummary[] }) {
  const router = useRouter();
  const [book, setBook] = useState(initial);
  const [view, setView] = useState<View>("single_season");
  const [busy, setBusy] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const team = book.team;

  async function retire(playerId: number, label: string) {
    setBusy(playerId);
    setError(null);
    setNotice(null);
    try {
      setBook(await api.retireNumber(team.id, playerId));
      setNotice(`${label} is retired: the ${team.nickname} won't issue it again.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader eyebrow="Record book" title={team.full_name}>
        <label className="flex items-center gap-2 text-sm">
          <span className="eyebrow">Team</span>
          <select className="field-input" value={team.id}
            onChange={(e) => router.push(`/records?team=${e.target.value}`)}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
          </select>
        </label>
      </PageHeader>
      {notice && <p role="status" className="mb-4 text-sm text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="mb-4 text-sm text-rose-300">{error}</p>}
      <div className="space-y-6">
        <Panel title="Records" action={
          <div role="tablist" aria-label="Records view" className="flex gap-1">
            {VIEWS.map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={view === key}
                className={`rounded-md px-3 py-1 text-xs font-semibold uppercase ${
                  view === key ? "bg-gold text-ink-950" : "text-mist hover:bg-white/5"}`}
                onClick={() => setView(key)}>
                {label}
              </button>
            ))}
          </div>
        }>
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {book.records.map((category) => {
              const rows: RecordRow[] = category[view] ?? [];
              return (
                <div key={category.key} role="group" aria-label={category.label}>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-mist">{category.label}</h3>
                  {rows.length === 0 ? <p className="text-sm text-mist">No games played yet.</p> : (
                    <ol className="space-y-1">
                      {rows.map((row, i) => <RecordLine key={`${row.player_id}-${row.year}-${i}`} row={row} rank={i + 1} />)}
                    </ol>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel title="Hall of Famers">
            {book.hall_of_famers.length === 0 ? (
              <p className="text-sm text-mist">None yet. <Link href="/hall-of-fame" className="text-gold hover:underline">The Hall of Fame →</Link></p>
            ) : (
              <ul className="space-y-2" aria-label="Hall of Famers">
                {book.hall_of_famers.map((f) => (
                  <li key={f.player_id} className="text-sm">
                    <Link href={`/players/${f.player_id}`} className="font-medium hover:text-gold">{f.name}</Link>
                    <span className="ml-1.5 text-xs text-mist">{f.position} · class of {f.year}</span>
                    <p className="text-xs text-mist">{f.case}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Retired numbers">
            {book.retired_numbers.length === 0 ? <p className="text-sm text-mist">None yet.</p> : (
              <ul className="space-y-1.5" aria-label="Retired numbers">
                {book.retired_numbers.map((r) => (
                  <li key={r.number} className="flex items-center gap-3 text-sm">
                    <span className="stat-number w-8 text-lg text-gold">{r.number}</span>
                    <Link href={`/players/${r.player_id}`} className="hover:text-gold">{r.name}</Link>
                    <span className="ml-auto text-xs text-mist">{r.year}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        {book.retire_candidates.length > 0 && (
          <Panel title="Retire a number">
            <p className="mb-3 text-sm text-mist">Former {team.nickname} players. A retired number is never issued again.</p>
            <ul className="divide-y divide-white/5" aria-label="Numbers you could retire">
              {book.retire_candidates.map((c) => (
                <li key={c.player_id} className="flex items-center gap-3 py-2 text-sm">
                  <TeamCrest team={team} size={18} />
                  <span className="stat-number w-8">{c.number}</span>
                  <span className="flex-1">
                    <span className="mr-1.5 text-xs text-mist">{c.position}</span>{c.name}
                    {c.hall_of_fame && <span className="ml-2 text-[10px] font-semibold uppercase text-gold">Hall of Fame</span>}
                  </span>
                  <button type="button" className="btn btn-ghost" disabled={busy !== null}
                    onClick={() => retire(c.player_id, `Number ${c.number}`)}>
                    Retire #{c.number}
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}
