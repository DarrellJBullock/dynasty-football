"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import { formatMoney, formatPhase } from "@/lib/format";
import type { FranchiseListItem } from "@/lib/types";

export function LeaguesHub({ initialFranchises }: { initialFranchises: FranchiseListItem[] }) {
  const router = useRouter();
  const [franchises, setFranchises] = useState(initialFranchises);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function activate(franchise: FranchiseListItem) {
    setBusyId(franchise.id);
    setError(null);
    try {
      await api.activateFranchise(franchise.id);
      // Switching franchises changes every page; a full load guarantees nothing stale.
      hardNavigate("/");
    } catch (e) {
      setError((e as Error).message);
      setBusyId(null);
    }
  }

  async function remove(franchise: FranchiseListItem) {
    setBusyId(franchise.id);
    setError(null);
    try {
      await api.deleteLeague(franchise.league.id);
      setFranchises((current) => current.filter((f) => f.id !== franchise.id));
      setConfirmingId(null);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">Saves</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Leagues & franchises</h1>
          <p className="mt-1 text-sm text-mist">Each league is its own career. Switch any time; progress is saved.</p>
        </div>
        <Link href="/leagues/new" className="btn btn-primary">+ Create league</Link>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
          {error}
        </p>
      )}

      <ul className="grid gap-4 md:grid-cols-2">
        {franchises.map((franchise) => (
          <li
            key={franchise.id}
            aria-label={franchise.name}
            className={`panel relative overflow-hidden p-5 ${franchise.is_active ? "ring-1 ring-gold/40" : ""}`}
          >
            <div
              className="pointer-events-none absolute inset-0 opacity-40"
              style={{ background: `radial-gradient(400px 160px at 0% 0%, ${franchise.team.primary_color}, transparent 70%)` }}
            />
            <div className="relative flex items-start gap-4">
              <TeamCrest team={franchise.team} size={52} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="truncate font-display text-2xl font-bold uppercase">{franchise.name}</h2>
                  {franchise.is_active && (
                    <span className="rounded bg-gold px-1.5 text-[10px] font-bold uppercase text-ink-950">Active</span>
                  )}
                </div>
                <p className="text-sm">{franchise.team.full_name}</p>
                <p className="text-xs text-mist">
                  {franchise.league.name}
                  {franchise.league.players === "women" && " · Women's league"} · {franchise.team_count} teams · {franchise.season.year}{" "}
                  {formatPhase(franchise.season.phase)} · {formatMoney(franchise.league.salary_cap)} cap
                </p>
              </div>
            </div>
            <div className="relative mt-4 flex flex-wrap justify-end gap-2">
              {!franchise.is_active && franchise.role === "commissioner" &&
                (confirmingId === franchise.id ? (
                  <>
                    <span className="mr-auto self-center text-xs text-rose-200">
                      Delete {franchise.league.name} and all its players?
                    </span>
                    <button type="button" className="btn btn-ghost" onClick={() => setConfirmingId(null)}>
                      Keep
                    </button>
                    <button type="button" className="btn btn-danger" disabled={busyId !== null}
                      onClick={() => remove(franchise)}>
                      {busyId === franchise.id ? "Deleting…" : "Delete league"}
                    </button>
                  </>
                ) : (
                  <button type="button" className="btn btn-ghost" onClick={() => setConfirmingId(franchise.id)}
                    aria-label={`Delete ${franchise.league.name}`}>
                    Delete
                  </button>
                ))}
              {franchise.is_active ? (
                <Link href="/" className="btn btn-ghost">Open dashboard</Link>
              ) : (
                confirmingId !== franchise.id && (
                  <button type="button" className="btn btn-primary" disabled={busyId !== null}
                    onClick={() => activate(franchise)}>
                    {busyId === franchise.id ? "Switching…" : "Switch to this franchise"}
                  </button>
                )
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
