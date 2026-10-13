"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { Turn } from "@/lib/types";

const when = new Intl.DateTimeFormat("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });

/**
 * The season together (a league with several managers): what's next, who's ready for it,
 * your own check-in, and, for a commissioner, advancing it. Nothing in a league you play
 * alone.
 */
export function TurnPanel({ leagueId }: { leagueId: number }) {
  const router = useRouter();
  const [turn, setTurn] = useState<Turn | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.turn(leagueId).then((found) => { if (live) setTurn(found); }, () => {});
    return () => { live = false; };
  }, [leagueId]);

  if (!turn || turn.managers.length < 2) return null;
  const you = turn.managers.find((m) => m.is_you);
  const ready = turn.managers.filter((m) => m.ready).length;

  async function act(action: () => Promise<Turn>, refresh = false) {
    setBusy(true);
    setError(null);
    try {
      setTurn(await action());
      if (refresh) router.refresh(); // (results change every page)
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="This step" className="mb-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-display text-lg font-semibold uppercase tracking-wide">Next: {turn.step}</h2>
        <span className="text-sm text-mist">
          {turn.all_ready ? "Everyone's ready" : `${ready} of ${turn.managers.length} ready`}
          {turn.next_advance_at && ` · advances ${when.format(new Date(turn.next_advance_at))}`}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          {you && (
            <button type="button" className={you.ready ? "btn btn-ghost" : "btn btn-primary"}
              aria-pressed={you.ready} disabled={busy}
              onClick={() => act(() => api.setReady(leagueId, !you.ready))}>
              {you.ready ? "Ready ✓" : "I'm ready"}
            </button>
          )}
          {turn.can_advance && (
            <button type="button" className={turn.all_ready ? "btn btn-primary" : "btn btn-ghost"}
              disabled={busy} onClick={() => act(() => api.advanceLeague(leagueId), true)}>
              {busy ? "Advancing…" : `Advance: ${turn.step}`}
            </button>
          )}
        </div>
      </div>
      <ul className="flex flex-wrap gap-2" aria-label="Managers">
        {turn.managers.map((m) => (
          <li key={m.member_id}
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
              m.ready ? "border-emerald-400/40 text-emerald-200" : "border-white/10 text-mist"}`}>
            <TeamCrest team={m.team} size={14} />
            {m.display_name}: {m.ready ? "ready" : "not yet"}
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
    </section>
  );
}
