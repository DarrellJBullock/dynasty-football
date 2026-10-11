"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type {
  ContractTerms,
  ExpiringContract,
  NegotiationResult,
  TeamContracts,
  TeamSummary,
} from "@/lib/types";

const MAX_YEARS = 5;

export function ContractsView({ data, team }: { data: TeamContracts; team: TeamSummary }) {
  const [negotiating, setNegotiating] = useState<ExpiringContract | null>(null);
  const { season } = data;
  const nextYear = season.year + 1;
  const pending = data.expiring.filter((row) => !row.re_signed);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <div className="eyebrow text-gold">{team.full_name}</div>
        <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Contracts</h1>
        <p className="mt-1 text-sm text-mist">
          {data.window_open
            ? `Re-signing is open. Players you don't re-sign leave in free agency when the ${nextYear} season starts.`
            : `${data.expiring.length} contract(s) expire after the ${season.year} season. Re-signing opens when the season is over.`}
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Salary cap">
        <CapStat label="Salary cap" value={data.salary_cap} />
        <CapStat label={`${season.year} payroll`} value={data.payroll} />
        <CapStat label={`Committed to ${nextYear}`} value={data.next_year_payroll} />
        <CapStat label={`${nextYear} cap space`} value={data.salary_cap - data.next_year_payroll}
          tone={data.salary_cap - data.next_year_payroll < 0 ? "bad" : "good"} />
      </section>

      <section className="panel p-5" aria-label="Expiring contracts">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="eyebrow">Expiring contracts</h2>
          {data.window_open && data.expiring.length > 0 && (
            <span className="text-xs text-mist">
              {data.expiring.length - pending.length} of {data.expiring.length} re-signed
            </span>
          )}
        </div>
        {data.expiring.length === 0 ? (
          <p className="text-sm text-mist">No contracts expire this year.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-mist">
                  <th className="py-2 pr-3 font-medium">Player</th>
                  <th className="px-2 font-medium">Age</th>
                  <th className="px-2 font-medium">OVR</th>
                  <th className="px-2 text-right font-medium">Current</th>
                  <th className="px-2 text-right font-medium">Asking</th>
                  <th className="py-2 pl-3 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.expiring.map((row) => (
                  <tr key={row.player.id} className="border-t border-white/5">
                    <td className="py-2 pr-3">
                      <PlayerName id={row.player.id} name={row.player.full_name} position={row.player.position} />
                    </td>
                    <td className="px-2 tabular-nums text-mist">{row.player.age}</td>
                    <td className="px-2"><OvrBadge value={row.player.overall} /></td>
                    <td className="px-2 text-right tabular-nums text-mist">
                      {row.player.contract && formatMoney(row.player.contract.salary)}
                    </td>
                    <td className="px-2 text-right tabular-nums">{terms(row.asking)}</td>
                    <td className="py-2 pl-3 text-right">
                      {row.re_signed ? (
                        <span className="text-xs font-semibold text-emerald-300">
                          Re-signed · {formatMoney(row.re_signed.salary)} × {row.re_signed.years}
                        </span>
                      ) : data.window_open ? (
                        <button type="button" className="btn btn-primary px-3 py-1 text-xs"
                          onClick={() => setNegotiating(row)}
                          aria-label={`Negotiate with ${row.player.full_name}`}>
                          Negotiate
                        </button>
                      ) : (
                        <span className="text-xs text-mist">After the season</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {(data.dead_money ?? []).length > 0 && (
        <section className="panel p-5" aria-label="Dead money">
          <h2 className="eyebrow mb-3">Dead money</h2>
          <p className="mb-3 text-sm text-mist">
            Signing bonus left on the cap by players no longer on the team.
          </p>
          <ul className="space-y-1 text-sm">
            {(data.dead_money ?? []).map((charge) => (
              <li key={`${charge.player_id}-${charge.year}`} className="flex items-center gap-3">
                <span className="w-12 tabular-nums text-mist">{charge.year}</span>
                <span className="flex-1">
                  <span className="mr-1.5 text-xs text-mist">{charge.position}</span>
                  {charge.name}
                  <span className="ml-2 text-xs text-mist">{charge.reason}</span>
                </span>
                <span className="tabular-nums text-rose-300">{formatMoney(charge.amount)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel p-5" aria-label="All contracts">
        <h2 className="eyebrow mb-3">All contracts</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-mist">
                <th className="py-2 pr-3 font-medium">Player</th>
                <th className="px-2 font-medium">Age</th>
                <th className="px-2 font-medium">OVR</th>
                <th className="px-2 text-right font-medium">Salary</th>
                <th className="px-2 text-right font-medium">Bonus</th>
                <th className="py-2 pl-3 text-right font-medium">Through</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((player) => (
                <tr key={player.id} className="border-t border-white/5">
                  <td className="py-1.5 pr-3">
                    <PlayerName id={player.id} name={player.full_name} position={player.position} />
                  </td>
                  <td className="px-2 tabular-nums text-mist">{player.age}</td>
                  <td className="px-2"><OvrBadge value={player.overall} /></td>
                  <td className="px-2 text-right tabular-nums">{player.contract && formatMoney(player.contract.salary)}</td>
                  <td className="px-2 text-right tabular-nums text-mist">
                    {player.contract?.signing_bonus ? formatMoney(player.contract.signing_bonus) : "—"}
                  </td>
                  <td className="py-1.5 pl-3 text-right tabular-nums text-mist">{player.contract?.end_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {negotiating && (
        <NegotiationDialog row={negotiating} capSpace={data.salary_cap - data.next_year_payroll}
          onClose={() => setNegotiating(null)} />
      )}
    </div>
  );
}

function terms({ salary, years }: ContractTerms): string {
  return `${formatMoney(salary)} × ${years} yr${years === 1 ? "" : "s"}`;
}

function PlayerName({ id, name, position }: { id: number; name: string; position: string }) {
  return (
    <Link href={`/players/${id}`} className="hover:text-gold">
      <span className="mr-1.5 text-xs text-mist">{position}</span>
      {name}
    </Link>
  );
}

function CapStat({ label, value, tone }: { label: string; value: number; tone?: "good" | "bad" }) {
  const color = tone === "bad" ? "text-rose-300" : tone === "good" ? "text-emerald-300" : "";
  return (
    <div className="panel p-4">
      <div className="eyebrow">{label}</div>
      <div className={`stat-number mt-1 text-2xl ${color}`}>{formatMoney(value)}</div>
    </div>
  );
}

function NegotiationDialog({ row, capSpace, onClose }: {
  row: ExpiringContract; capSpace: number; onClose: () => void;
}) {
  const router = useRouter();
  const { player, asking } = row;
  const [years, setYears] = useState(asking.years);
  const [millions, setMillions] = useState((asking.salary / 1_000_000).toFixed(2));
  const [result, setResult] = useState<NegotiationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const salary = Math.round(Number(millions) * 100) * 10_000; // $10k steps

  async function offer(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.reSign(player.id, { salary, years });
      setResult(response);
      if (response.counter) setMillions((response.counter.salary / 1_000_000).toFixed(2));
      if (response.accepted) router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Re-sign ${player.full_name}`} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-mist">
          {player.position} · Age {player.age} · {player.overall} OVR · asking {terms(asking)} ·{" "}
          {formatMoney(capSpace)} cap space next season
        </p>
        <p className="text-xs text-mist">
          Deals above the minimum include a signing bonus of 30% of their total value: the cap
          hit stays the salary, but the bonus is guaranteed — cut him early and the rest of it
          stays on your cap as dead money.
        </p>
        {result?.accepted ? (
          <div className="space-y-4">
            <p role="status" className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-200">{result.message}</p>
            <button type="button" className="btn btn-primary" onClick={onClose}>Done</button>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={offer}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="eyebrow mb-1 block">Years</span>
                <select className="field-input w-full" value={years}
                  onChange={(e) => setYears(Number(e.target.value))}>
                  {Array.from({ length: MAX_YEARS }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>{n} year{n === 1 ? "" : "s"}</option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <span className="eyebrow mb-1 block">Salary per year ($M)</span>
                <input className="field-input w-full" type="number" min={0.75} step={0.01}
                  value={millions} onChange={(e) => setMillions(e.target.value)} />
              </label>
            </div>
            {result && !result.accepted && (
              <p role="status" className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-200">{result.message}</p>
            )}
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={busy || !(salary > 0)}>
                {busy ? "Offering…" : `Offer ${formatMoney(salary)} × ${years}`}
              </button>
            </div>
          </form>
        )}
      </div>
    </Dialog>
  );
}
