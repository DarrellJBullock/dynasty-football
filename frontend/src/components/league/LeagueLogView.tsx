"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { formatAttribute, formatMoney } from "@/lib/format";
import type { LeagueLog, LeagueLogAction, LeagueLogEntry } from "@/lib/types";

const when = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
});

export const ACTION_LABELS: Record<LeagueLogAction, string> = {
  player: "Player edit", new_player: "New player", move: "Player moved", contract: "Contract",
  team: "Team edit", import: "Roster import", veto: "Trade vetoed", approve: "Trade approved",
  settings: "Settings", member: "Members",
};

function value(field: string, v: LeagueLogEntry["changes"][number]["before"]): string {
  if (v === null || v === undefined) return "—";
  if (field === "salary" || field === "staff_budget") return formatMoney(Number(v));
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

/**
 * The League log: every edit to a player or team and every commissioner action, newest
 * first, for every member to see.
 */
export function LeagueLogView({ leagueId, initial }: { leagueId: number; initial: LeagueLog }) {
  const [log, setLog] = useState(initial);
  const [action, setAction] = useState<LeagueLogAction | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(next: LeagueLogAction | "", before?: number) {
    setBusy(true);
    setError(null);
    try {
      const page = await api.leagueLog(leagueId, { action: next || undefined, before });
      setLog((current) => before ? { entries: [...current.entries, ...page.entries], more: page.more } : page);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">The league</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">League log</h1>
          <p className="mt-1 text-sm text-mist">
            Every edit to a player or team, and everything the commissioner does, for every
            member to see.
          </p>
        </div>
        <label className="text-xs text-mist">
          Show
          <select className="input ml-2 w-auto" value={action} onChange={(e) => {
            const next = e.target.value as LeagueLogAction | "";
            setAction(next);
            load(next);
          }}>
            <option value="">Everything</option>
            {(Object.keys(ACTION_LABELS) as LeagueLogAction[]).map((key) => (
              <option key={key} value={key}>{ACTION_LABELS[key]}</option>
            ))}
          </select>
        </label>
      </div>

      <section className="panel p-0" aria-label="League log entries" aria-busy={busy}>
        {log.entries.length === 0 ? (
          <p className="p-6 text-sm text-mist">Nothing yet: edits and commissioner actions show up here.</p>
        ) : (
          <ol className="divide-y divide-white/[0.05]">
            {log.entries.map((entry) => (
              <li key={entry.id} className="space-y-2 px-5 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm">
                    <span className="font-semibold">{entry.actor}</span>{" "}
                    {entry.player_id ? (
                      <Link href={`/players/${entry.player_id}`} className="hover:text-gold">{entry.summary}</Link>
                    ) : entry.summary}
                  </p>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-mist">
                    <span className="rounded bg-white/[0.06] px-1.5 py-0.5">{ACTION_LABELS[entry.action] ?? entry.action}</span>
                    {when.format(new Date(entry.created_at))}
                  </span>
                </div>
                {entry.changes.length > 0 && (
                  <table className="w-full max-w-lg text-xs">
                    <caption className="sr-only">What changed</caption>
                    <thead>
                      <tr className="text-left text-mist">
                        <th scope="col" className="py-0.5 font-normal">Field</th>
                        <th scope="col" className="py-0.5 font-normal">Before</th>
                        <th scope="col" className="py-0.5 font-normal">After</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entry.changes.map((c) => (
                        <tr key={c.field}>
                          <th scope="row" className="py-0.5 pr-4 text-left font-normal">{formatAttribute(c.field)}</th>
                          <td className="py-0.5 pr-4 text-mist">{value(c.field, c.before)}</td>
                          <td className="py-0.5">{value(c.field, c.after)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      {log.more && (
        <div className="text-center">
          <button type="button" className="btn btn-ghost" disabled={busy}
            onClick={() => load(action, log.entries.at(-1)?.id)}>
            {busy ? "Loading…" : "Older entries"}
          </button>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
    </div>
  );
}
