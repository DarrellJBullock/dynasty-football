"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Finances, TicketPrice } from "@/lib/types";

function Signed({ amount }: { amount: number }) {
  return (
    <span className={amount < 0 ? "text-rose-300" : "text-emerald-300"}>
      {amount < 0 ? "−" : "+"}{formatMoney(Math.abs(amount))}
    </span>
  );
}

/**
 * The team's money this season: each home game's gate, the media share, merchandise, what
 * the players and staff cost, the profit so far and at this pace, and past seasons. Money
 * never limits spending (the cap does); the owner judges the season by it.
 */
export function FinancesView({ initial, canSetPrice }: { initial: Finances; canSetPrice: boolean }) {
  const router = useRouter();
  const [finances, setFinances] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const f = finances;

  async function choose(price: TicketPrice) {
    setBusy(true);
    setError(null);
    try {
      setFinances(await api.setTicketPrice(f.team.id, price));
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const played = Math.round(f.share * 100);
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader eyebrow={`${f.season_year ?? ""} season · ${f.market} market`} title="Finances">
        <TeamCrest team={f.team} size={40} />
      </PageHeader>

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4" role="group" aria-label="This season">
        {[
          ["Revenue so far", formatMoney(f.total_revenue)],
          ["Expenses so far", formatMoney(f.total_expenses)],
        ].map(([label, value]) => (
          <section key={label} className="panel p-5" aria-label={label}>
            <h2 className="eyebrow">{label}</h2>
            <p className="stat-number mt-2 text-3xl">{value}</p>
            <p className="text-xs text-mist">{played}% of the regular season played</p>
          </section>
        ))}
        <section className="panel p-5" aria-label="Profit so far">
          <h2 className="eyebrow">Profit so far</h2>
          <p className="stat-number mt-2 text-3xl"><Signed amount={f.profit} /></p>
        </section>
        <section className="panel p-5" aria-label="At this pace">
          <h2 className="eyebrow">At this pace</h2>
          <p className="stat-number mt-2 text-3xl"><Signed amount={f.projected_profit} /></p>
          <p className="text-xs text-mist">The rest of the home games at today&apos;s gate, a full season&apos;s costs</p>
        </section>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Panel title="Revenue">
          <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-sm">
            {f.revenue.map((line) => (
              <div key={line.label} className="contents">
                <dt className="text-mist">{line.label}</dt><dd className="tabular-nums">{formatMoney(line.amount)}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <Panel title="Expenses">
          <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-sm">
            {f.expenses.map((line) => (
              <div key={line.label} className="contents">
                <dt className="text-mist">{line.label}</dt><dd className="tabular-nums">{formatMoney(line.amount)}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <section className="panel space-y-3 p-5" aria-label="Ticket prices">
          <h2 className="eyebrow">Ticket prices</h2>
          <div role="radiogroup" aria-label="Ticket price" className="flex gap-2">
            {f.prices.map((p) => (
              <button key={p.price} type="button" role="radio" aria-checked={f.ticket_price === p.price}
                disabled={busy || !canSetPrice || f.price_locked !== null}
                onClick={() => choose(p.price)}
                className={`flex-1 rounded-lg border px-3 py-2 text-left text-sm disabled:cursor-not-allowed ${
                  f.ticket_price === p.price ? "border-gold/60 bg-gold/[0.08]" : "border-white/10 bg-white/[0.03]"}`}>
                <span className="block font-semibold">{p.label}</span>
                <span className="text-xs text-mist">${p.seat} a seat</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-mist">
            Cheaper tickets fill the {f.capacity.toLocaleString("en-US")}-seat stadium and lift the
            fans&apos; mood; dearer ones earn more a seat.
          </p>
          {f.price_locked && <p className="text-xs text-mist">{f.price_locked}</p>}
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        </section>
      </div>

      <Panel title="Home games" className="mt-6">
        {f.gates.length === 0 ? (
          <p className="text-sm text-mist">No home game played yet this season.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">Each home game&apos;s gate</caption>
            <thead>
              <tr className="text-left text-xs text-mist">
                <th scope="col" className="py-1 font-normal">Game</th>
                <th scope="col" className="py-1 font-normal">Fan mood</th>
                <th scope="col" className="py-1 font-normal">Attendance</th>
                <th scope="col" className="py-1 text-right font-normal">Gate</th>
              </tr>
            </thead>
            <tbody>
              {f.gates.map((g) => (
                <tr key={g.game_id} className="border-t border-white/[0.04]">
                  <th scope="row" className="py-1 text-left font-normal">
                    {g.playoff ? "Playoffs" : `Week ${g.week}`} vs {g.opponent}
                  </th>
                  <td className="py-1 tabular-nums">{g.fan_mood}</td>
                  <td className="py-1 tabular-nums">
                    {g.attendance.toLocaleString("en-US")} ({Math.round((100 * g.attendance) / g.capacity)}%)
                  </td>
                  <td className="py-1 text-right tabular-nums">{formatMoney(g.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {f.history.length > 0 && (
        <Panel title="Past seasons" className="mt-6">
          <table className="w-full text-sm">
            <caption className="sr-only">Each past season&apos;s money</caption>
            <thead>
              <tr className="text-left text-xs text-mist">
                <th scope="col" className="py-1 font-normal">Season</th>
                <th scope="col" className="py-1 text-right font-normal">Revenue</th>
                <th scope="col" className="py-1 text-right font-normal">Expenses</th>
                <th scope="col" className="py-1 text-right font-normal">Profit</th>
              </tr>
            </thead>
            <tbody>
              {f.history.map((h) => (
                <tr key={h.year} className="border-t border-white/[0.04]">
                  <th scope="row" className="py-1 text-left font-normal">{h.year}</th>
                  <td className="py-1 text-right tabular-nums">{formatMoney(h.revenue)}</td>
                  <td className="py-1 text-right tabular-nums">{formatMoney(h.expenses)}</td>
                  <td className="py-1 text-right tabular-nums"><Signed amount={h.profit} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
