"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { SimControls } from "@/components/season/SimControls";
import { Dialog } from "@/components/ui/Dialog";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { POSITIONS } from "@/lib/types";
import type { ContractTerms, FreeAgencyOut, FreeAgentRow, TeamSummary } from "@/lib/types";

const MAX_YEARS = 5;
const SHOWN = 120; // rows per position filter; the pool is sorted best first

export function FreeAgencyView({ market, team }: { market: FreeAgencyOut; team: TeamSummary }) {
  const [position, setPosition] = useState<string>("");
  const [offering, setOffering] = useState<FreeAgentRow | null>(null);
  const rows = market.players.filter((r) => !position || r.player.position === position);
  const myOffers = market.players.filter((r) => r.my_offer);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{team.full_name}</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Free Agency</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist">
            {market.open
              ? `Day ${market.day} of ${market.days}. Players want ${Math.round((market.demand ?? 1) * 100)}% ` +
                "of their asking price today and take less as the market goes on; each picks the best " +
                "offer, leaning toward stronger teams. Open spots left at the end go to undrafted rookies."
              : "Sign free agents at their asking price. When the season ends, free agency opens " +
                "after re-signing and teams bid against each other."}
          </p>
        </div>
        {market.open && <SimControls season={market.season} teamId={team.id} />}
      </div>

      <section className="grid gap-4 sm:grid-cols-3" aria-label="Your situation">
        <Stat label="Cap space" value={formatMoney(market.cap_space)} />
        <Stat label="Open roster spots" value={String(market.open_spots)} />
        <Stat label="Your offers" value={String(myOffers.length)} />
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="panel p-5" aria-label="Free agents">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="eyebrow">Free agents ({rows.length})</h2>
            <label className="flex items-center gap-2 text-xs text-mist">
              Position
              <select className="field-input py-1 text-xs" value={position}
                onChange={(e) => setPosition(e.target.value)}>
                <option value="">All</option>
                {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-mist">
                  <th className="py-2 pr-3 font-medium">Player</th>
                  <th className="px-2 font-medium">Age</th>
                  <th className="px-2 font-medium">OVR</th>
                  <th className="px-2 text-right font-medium">Asking</th>
                  {market.open && <th className="px-2 text-right font-medium">Offers</th>}
                  <th className="py-2 pl-3 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, SHOWN).map((row) => (
                  <PlayerRow key={row.player.id} row={row} open={market.open} teamId={team.id}
                    onOffer={() => setOffering(row)} />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel p-5" aria-label="Signings">
          <h2 className="eyebrow mb-3">Signings this offseason</h2>
          {market.signings.length === 0 ? (
            <p className="text-sm text-mist">No free agents have signed yet.</p>
          ) : (
            <ul className="space-y-2">
              {market.signings.slice(0, 40).map((s) => (
                <li key={s.player.id} className={`flex items-center gap-2 text-sm ${s.team.id === team.id ? "text-gold" : ""}`}>
                  <TeamCrest team={s.team} size={20} />
                  <Link href={`/players/${s.player.id}`} className="min-w-0 flex-1 truncate hover:text-gold">
                    <span className="mr-1.5 text-xs text-mist">{s.player.position}</span>
                    {s.player.full_name}
                  </Link>
                  <span className="text-xs tabular-nums text-mist">
                    {formatMoney(s.salary)} × {s.years} · D{s.day}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {offering && (
        <OfferDialog row={offering} demand={market.demand ?? 1} capSpace={market.cap_space}
          onClose={() => setOffering(null)} />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-4">
      <div className="eyebrow">{label}</div>
      <div className="stat-number mt-1 text-2xl">{value}</div>
    </div>
  );
}

function terms({ salary, years }: ContractTerms): string {
  return `${formatMoney(salary)} × ${years}`;
}

function PlayerRow({ row, open, teamId, onOffer }: {
  row: FreeAgentRow; open: boolean; teamId: number; onOffer: () => void;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const { player } = row;

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <tr className="border-t border-white/5">
      <td className="py-1.5 pr-3">
        <Link href={`/players/${player.id}`} className="hover:text-gold">
          <span className="mr-1.5 text-xs text-mist">{player.position}</span>
          {player.full_name}
        </Link>
        {error && <div role="alert" className="text-xs text-rose-300">{error}</div>}
      </td>
      <td className="px-2 tabular-nums text-mist">{player.age}</td>
      <td className="px-2"><OvrBadge value={player.overall} /></td>
      <td className="px-2 text-right tabular-nums">{terms(row.asking)}</td>
      {open && <td className="px-2 text-right tabular-nums text-mist">{row.offers}</td>}
      <td className="py-1.5 pl-3 text-right">
        {!open ? (
          <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
            aria-label={`Sign ${player.full_name}`}
            onClick={() => act(() => api.signPlayer(teamId, player.id, row.asking.years))}>
            Sign
          </button>
        ) : row.my_offer ? (
          <span className="flex items-center justify-end gap-2 text-xs">
            <span className={row.leading ? "text-emerald-300" : "text-amber-300"}>
              {terms(row.my_offer)} · {row.leading ? "Leading" : "Outbid"}
            </span>
            <button type="button" className="text-gold hover:underline" onClick={onOffer}
              aria-label={`Change offer to ${player.full_name}`}>Change</button>
            <button type="button" className="text-mist hover:text-rose-300"
              aria-label={`Withdraw offer to ${player.full_name}`}
              onClick={() => act(() => api.withdrawOffer(player.id))}>✕</button>
          </span>
        ) : (
          <button type="button" className="btn btn-primary px-3 py-1 text-xs" onClick={onOffer}
            aria-label={`Make an offer to ${player.full_name}`}>
            Offer
          </button>
        )}
      </td>
    </tr>
  );
}

function OfferDialog({ row, demand, capSpace, onClose }: {
  row: FreeAgentRow; demand: number; capSpace: number; onClose: () => void;
}) {
  const router = useRouter();
  const { player, asking } = row;
  const start = row.my_offer ?? { years: asking.years, salary: asking.salary * demand };
  const [years, setYears] = useState(start.years);
  const [millions, setMillions] = useState((Math.round(start.salary / 10_000) / 100).toFixed(2));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const salary = Math.round(Number(millions) * 100) * 10_000;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.makeOffer(player.id, { salary, years });
      router.refresh();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Offer ${player.full_name}`} onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <p className="text-sm text-mist">
          {player.position} · Age {player.age} · {player.overall} OVR · asking {terms(asking)} ·{" "}
          {row.offers} offer(s) so far · {formatMoney(capSpace)} cap space. The decision comes when the day
          is played; other lengths cost more.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="eyebrow mb-1 block">Years</span>
            <select className="field-input w-full" value={years} onChange={(e) => setYears(Number(e.target.value))}>
              {Array.from({ length: MAX_YEARS }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n} year{n === 1 ? "" : "s"}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="eyebrow mb-1 block">Salary per year ($M)</span>
            <input className="field-input w-full" type="number" min={0.75} step={0.01} value={millions}
              onChange={(e) => setMillions(e.target.value)} />
          </label>
        </div>
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy || !(salary > 0)}>
            {busy ? "Sending…" : `Offer ${formatMoney(salary)} × ${years}`}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
