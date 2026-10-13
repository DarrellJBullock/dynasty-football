"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { SeasonTrade } from "@/lib/types";

/**
 * The commissioner's view of every trade this season: each can be reversed (everything goes
 * back) until someone in it moves on, which it then says.
 */
export function SeasonTrades({ trades }: { trades: SeasonTrade[] }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reverse(trade: SeasonTrade) {
    setBusy(true);
    setError(null);
    try {
      await api.reverseTrade(trade.id);
      setNotice(`Reversed: the ${trade.team.nickname} and the ${trade.partner.nickname} have everyone back.`);
      setConfirming(null);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel p-5" aria-label="This season's trades">
      <h2 className="eyebrow mb-1">This season&apos;s trades</h2>
      <p className="mb-3 text-xs text-mist">
        As commissioner you can reverse a trade from this season while everyone in it is still
        where it sent them. It goes in the League log.
      </p>
      <ul className="divide-y divide-white/[0.05] text-sm">
        {trades.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center gap-2 py-2">
            <TeamCrest team={t.team} size={18} />
            <span className="text-mist">{t.team.abbreviation}</span>
            <span>sent {t.sent.map((i) => i.label).join(", ") || "nothing"}</span>
            <span className="text-mist">to</span>
            <TeamCrest team={t.partner} size={18} />
            <span className="text-mist">{t.partner.abbreviation}</span>
            <span>for {t.received.map((i) => i.label).join(", ") || "nothing"}</span>
            <span className="ml-auto flex items-center gap-2">
              {t.reversed ? (
                <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-xs text-mist">Reversed</span>
              ) : t.problem ? (
                <span className="text-xs text-mist">{t.problem}</span>
              ) : confirming === t.id ? (
                <>
                  <button type="button" className="btn btn-danger px-3 py-1 text-xs" disabled={busy}
                    onClick={() => reverse(t)}>Confirm: reverse it</button>
                  <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
                    onClick={() => setConfirming(null)}>Cancel</button>
                </>
              ) : (
                <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
                  aria-label={`Reverse the trade between the ${t.team.nickname} and the ${t.partner.nickname}`}
                  onClick={() => setConfirming(t.id)}>Reverse</button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {notice && <p role="status" className="mt-2 text-sm text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="mt-2 text-sm text-rose-300">{error}</p>}
    </section>
  );
}
