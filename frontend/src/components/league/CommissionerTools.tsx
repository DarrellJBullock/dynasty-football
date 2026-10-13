"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PlayerEditForm } from "@/components/roster/PlayerPanel";
import { Dialog } from "@/components/ui/Dialog";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { PlayerDetail } from "@/lib/types";

const FREE_AGENCY = "free";

/**
 * The commissioner's edits on a player's page: his ratings and bio, his team (or free
 * agency), and his contract. Each goes in the League log for every member to see.
 */
export function CommissionerTools({ player: initial, teams }: {
  player: PlayerDetail;
  teams: { id: number; full_name: string }[];
}) {
  const router = useRouter();
  // (his state as the last edit left it; the page refreshes around it)
  const [player, setPlayer] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [team, setTeam] = useState(player.team_id === null ? FREE_AGENCY : String(player.team_id));
  const [salary, setSalary] = useState(((player.contract?.salary ?? 1_000_000) / 1_000_000).toFixed(2));
  const [years, setYears] = useState(Math.max(1, player.contract?.years ?? 1));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(request: () => Promise<PlayerDetail>, done: (p: PlayerDetail) => string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await request();
      setPlayer(updated);
      setTeam(updated.team_id === null ? FREE_AGENCY : String(updated.team_id));
      setNotice(done(updated));
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const teamName = (id: number | null) =>
    id === null ? "free agency" : teams.find((t) => t.id === id)?.full_name ?? "his new team";
  const moveTo = team === FREE_AGENCY ? null : Number(team);
  const dollars = Math.round(Number(salary) * 1_000_000);

  return (
    <section className="panel space-y-4 p-6" aria-label="Commissioner">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-bold uppercase">Commissioner</h2>
        <p className="text-xs text-mist">
          Every change goes in the <Link href="/league-log" className="text-gold hover:underline">League log</Link>.
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Ratings and bio</h3>
          <p className="text-xs text-mist">Position, age, injury, development and every rating.</p>
          <button type="button" className="btn btn-ghost" onClick={() => setEditing(true)}>Edit player</button>
        </div>

        <form className="space-y-2" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.movePlayer(player.id, moveTo), (p) => `Moved to ${teamName(p.team_id)}.`);
        }}>
          <h3 className="text-sm font-semibold">Team</h3>
          <label className="block text-xs text-mist">
            Move to
            <select className="input mt-1 w-full" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value={FREE_AGENCY}>Free agency</option>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            </select>
          </label>
          <button type="submit" className="btn btn-ghost"
            disabled={busy || moveTo === player.team_id}>Move player</button>
        </form>

        <form className="space-y-2" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.setContract(player.id, dollars, years),
            (p) => `Contract: ${formatMoney(p.contract?.salary ?? dollars)} a season through ${p.contract?.end_year}.`);
        }}>
          <h3 className="text-sm font-semibold">Contract</h3>
          {player.team_id === null ? (
            <p className="text-xs text-mist">A free agent has no contract; move him to a team first.</p>
          ) : (
            <>
              <div className="flex gap-2">
                <label className="block flex-1 text-xs text-mist">
                  Salary ($M a season)
                  <input className="input mt-1 w-full" type="number" min="0.75" max="100" step="0.05"
                    value={salary} onChange={(e) => setSalary(e.target.value)} />
                </label>
                <label className="block text-xs text-mist">
                  Years
                  <select className="input mt-1" value={years} onChange={(e) => setYears(Number(e.target.value))}>
                    {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
              </div>
              <button type="submit" className="btn btn-ghost" disabled={busy}>Save contract</button>
            </>
          )}
        </form>
      </div>

      {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}

      {editing && (
        <Dialog title="Edit player" onClose={() => setEditing(false)}>
          <PlayerEditForm player={player} onCancel={() => setEditing(false)} onSaved={(saved) => {
            setPlayer(saved);
            setEditing(false);
            setNotice("Saved.");
            router.refresh();
          }} />
        </Dialog>
      )}
    </section>
  );
}
