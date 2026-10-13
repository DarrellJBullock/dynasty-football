"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { SimControls } from "@/components/season/SimControls";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { formatHeight } from "@/lib/format";
import { POSITIONS } from "@/lib/types";
import type { DraftOut, DraftPickOut, ProspectRow, TeamSummary } from "@/lib/types";

const SHOWN = 150;

const clockTime = new Intl.DateTimeFormat("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });

export function DraftView({ draft, team, leagueId, canRun = true }: {
  draft: DraftOut; team: TeamSummary; leagueId: number; canRun?: boolean;
}) {
  const router = useRouter();
  const [position, setPosition] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const live = draft.status === "live";
  const clock = draft.picks.find((p) => p.number === draft.on_the_clock);
  const mine = draft.picks.filter((p) => p.team.id === draft.my_team_id);
  const myTurn = live && clock?.team.id === draft.my_team_id;
  const prospects = draft.prospects.filter((p) => !position || p.position === position);
  const made = draft.picks.filter((p) => p.player).reverse();
  const over = draft.roster_count - draft.roster_max;

  async function act(playerId: number, action: () => Promise<unknown>) {
    setBusy(playerId);
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{team.full_name}</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">{draft.year} Draft</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist" role="status" aria-label="Draft status">
            {draft.status === "upcoming" &&
              `Held after free agency, ${draft.picks.length || 7} rounds. Projections are ranges until ` +
              `you scout a prospect: ${draft.scouting_left} scouting report(s) left for this class.`}
            {live && clock && (myTurn
              ? `You're on the clock: round ${clock.round}, pick ${clock.pick_in_round} (#${clock.number}).`
              : `On the clock: ${clock.team.full_name} (#${clock.number}).` +
                (draft.my_next_pick ? ` Your next pick: #${draft.my_next_pick}.` : ""))}
            {live && draft.clock_ends_at &&
              ` The clock runs out ${clockTime.format(new Date(draft.clock_ends_at))}; then the pick is made by need.`}
            {draft.status === "complete" && "The draft is complete."}
          </p>
        </div>
        {live && <SimControls season={draft.season} teamId={team.id} canRun={canRun} />}
      </div>

      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}

      {draft.status === "complete" && over > 0 && (
        <section className="panel flex flex-wrap items-center gap-3 p-4" aria-label="Roster cut-down">
          <span className="text-sm">
            Your roster has {draft.roster_count} players; cut {over} to get to {draft.roster_max} before
            week 1.
          </span>
          <button type="button" className="btn btn-primary px-3 py-1 text-xs"
            onClick={() => act(0, () => api.cutDown(team.id))}>
            Auto-cut to {draft.roster_max}
          </button>
          <Link href="/roster" className="text-sm text-gold hover:underline">Or choose on the roster →</Link>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="panel p-5" aria-label="Prospects">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="eyebrow">Prospects ({prospects.length}) · {draft.scouting_left} scouting reports left</h2>
            <label className="flex items-center gap-2 text-xs text-mist">
              Position
              <select className="field-input py-1 text-xs" value={position} onChange={(e) => setPosition(e.target.value)}>
                <option value="">All</option>
                {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
          {prospects.length === 0 ? (
            <p className="text-sm text-mist">No prospects left.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-mist">
                    <th className="py-2 pr-3 font-medium">Prospect</th>
                    <th className="px-2 font-medium">Age</th>
                    <th className="px-2 font-medium">Size</th>
                    <th className="px-2 font-medium">Projected</th>
                    <th className="px-2 font-medium">Potential</th>
                    <th className="py-2 pl-3 text-right font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {prospects.slice(0, SHOWN).map((p) => (
                    <ProspectLine key={p.id} prospect={p} canScout={draft.scouting_left > 0}
                      canDraft={myTurn} busy={busy === p.id}
                      onScout={() => act(p.id, () => api.scout(p.id))}
                      onDraft={() => act(p.id, () => api.draftPick(leagueId, p.id))} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="space-y-6">
          <section className="panel p-5" aria-label="Your picks">
            <h2 className="eyebrow mb-3">Your picks</h2>
            {mine.length === 0 ? (
              <p className="text-sm text-mist">The order is set when free agency ends.</p>
            ) : (
              <ul className="space-y-1.5">{mine.map((p) => <PickLine key={p.number} pick={p} />)}</ul>
            )}
          </section>
          {made.length > 0 && (
            <section className="panel p-5" aria-label="Picks made">
              <h2 className="eyebrow mb-3">Latest picks</h2>
              <ul className="space-y-1.5">{made.slice(0, 32).map((p) => <PickLine key={p.number} pick={p} showTeam />)}</ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function ProspectLine({ prospect: p, canScout, canDraft, busy, onScout, onDraft }: {
  prospect: ProspectRow; canScout: boolean; canDraft: boolean; busy: boolean;
  onScout: () => void; onDraft: () => void;
}) {
  return (
    <tr className="border-t border-white/5">
      <td className="py-1.5 pr-3">
        <span className="mr-1.5 text-xs text-mist">{p.position}</span>
        {p.full_name}
        <div className="text-xs text-mist">{p.college}</div>
      </td>
      <td className="px-2 tabular-nums text-mist">{p.age}</td>
      <td className="px-2 text-xs tabular-nums text-mist">{formatHeight(p.height_in)}, {p.weight_lb}</td>
      <td className="px-2">
        {p.scouted ? <OvrBadge value={p.projected} /> : (
          <span className="tabular-nums" title="Projection range until scouted">{p.low}–{p.high}</span>
        )}
      </td>
      <td className="px-2 tabular-nums">
        {p.scouted ? <span title={`Potential ${p.potential}`}>{p.potential} ({p.grade})</span> : p.grade}
      </td>
      <td className="py-1.5 pl-3 text-right">
        <span className="flex items-center justify-end gap-2">
          {p.scouted ? (
            <span className="text-[10px] font-semibold uppercase text-emerald-300">Scouted</span>
          ) : (
            <button type="button" className="btn btn-ghost px-2 py-0.5 text-xs" disabled={!canScout || busy}
              onClick={onScout} aria-label={`Scout ${p.full_name}`}>
              Scout
            </button>
          )}
          {canDraft && (
            <button type="button" className="btn btn-primary px-2 py-0.5 text-xs" disabled={busy}
              onClick={onDraft} aria-label={`Draft ${p.full_name}`}>
              Draft
            </button>
          )}
        </span>
      </td>
    </tr>
  );
}

function PickLine({ pick, showTeam = false }: { pick: DraftPickOut; showTeam?: boolean }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className="w-14 shrink-0 text-xs tabular-nums text-mist">R{pick.round} #{pick.number}</span>
      {showTeam && <TeamCrest team={pick.team} size={18} />}
      {pick.original_team && (
        <span className="shrink-0 text-[10px] uppercase text-mist">via {pick.original_team.abbreviation}</span>
      )}
      {pick.player ? (
        <Link href={`/players/${pick.player.id}`} className="min-w-0 flex-1 truncate hover:text-gold">
          <span className="mr-1.5 text-xs text-mist">{pick.player.position}</span>
          {pick.player.full_name}
        </Link>
      ) : (
        <span className="flex-1 text-mist">—</span>
      )}
      {pick.player && <OvrBadge value={pick.player.overall} />}
    </li>
  );
}
