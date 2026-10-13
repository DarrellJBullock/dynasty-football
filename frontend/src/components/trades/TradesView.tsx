"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { TradeOffers } from "./TradeOffers";
import { formatMoney } from "@/lib/format";
import type {
  TeamSummary,
  TradeAssetOut,
  TradeAssets,
  TradeCenter,
  TradeEvaluation,
  TradeOffer,
  TradeProposal,
} from "@/lib/types";

type Side = "send" | "receive";
type Selection = Record<Side, { players: number[]; picks: number[] }>;

const EMPTY: Selection = { send: { players: [], picks: [] }, receive: { players: [], picks: [] } };

/** The selection a counter-offer starts from: the offer with the sides swapped. */
export function counterSelection(offer: TradeOffer): Selection {
  const ids = (items: TradeOffer["gives"], kind: "player" | "pick") =>
    items.filter((i) => i.kind === kind).map((i) => i.id);
  return {
    send: { players: ids(offer.gets, "player"), picks: ids(offer.gets, "pick") },
    receive: { players: ids(offer.gives, "player"), picks: ids(offer.gives, "pick") },
  };
}

export function TradesView({ center, team, leagueId, commissioner = false, counterId }: {
  center: TradeCenter; team: TeamSummary; leagueId: number;
  /** The viewer is a commissioner (vetoes trades in the veto window). */
  commissioner?: boolean;
  /** Counter this incoming offer: the deal starts from it, sides swapped. */
  counterId?: number;
}) {
  const router = useRouter();
  const countering = center.offers.find((o) => o.id === counterId && o.direction === "incoming"
    && o.status === "pending" && o.from_team.id === center.partner?.id);
  const [selection, setSelection] = useState<Selection>(
    countering ? counterSelection(countering) : EMPTY);
  const [note, setNote] = useState("");
  const [evaluation, setEvaluation] = useState<TradeEvaluation | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const partner = center.partner;
  const managed = !!partner && center.managed.includes(partner.id);
  const proposal: TradeProposal | null = partner && {
    partner_id: partner.id,
    send_players: selection.send.players, send_picks: selection.send.picks,
    receive_players: selection.receive.players, receive_picks: selection.receive.picks,
  };
  const empty = !proposal || Object.values(selection).every((s) => !s.players.length && !s.picks.length);
  const key = JSON.stringify(proposal);

  useEffect(() => {
    if (empty || !proposal) return;
    let live = true;
    const timer = setTimeout(() => {
      api.evaluateTrade(leagueId, proposal)
        .then((result) => live && setEvaluation(result))
        .catch((e: Error) => live && setError(e.message));
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures the proposal
  }, [key, empty, leagueId]);

  function toggle(side: Side, kind: "players" | "picks", id: number) {
    setStatus(null);
    setError(null);
    setSelection((current) => {
      const list = current[side][kind];
      const next = list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
      return { ...current, [side]: { ...current[side], [kind]: next } };
    });
  }

  async function propose() {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      if (managed) {
        await (countering ? api.counterOffer(countering.id, proposal, note)
          : api.makeTradeOffer(leagueId, proposal, note));
        setSelection(EMPTY);
        setEvaluation(null);
        setNote("");
        setStatus(`${countering ? "Counter-offer" : "Offer"} sent to ${center.partner_manager}.`);
        // The offers list changes; a counter also leaves the countered offer behind.
        if (countering) router.replace(`/trades?partner=${partner?.id}`);
        else router.refresh();
        return;
      }
      const result = await api.proposeTrade(leagueId, proposal);
      if (result.accepted) {
        setSelection(EMPTY);
        setEvaluation(null);
        setStatus(`Trade done with the ${partner?.nickname}.`);
        router.refresh();
      } else {
        setEvaluation(result.evaluation);
        setStatus(result.evaluation.message);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const shown = empty ? null : evaluation;
  const picked = (assets: TradeAssets, side: Side) => [
    ...assets.players.filter((a) => selection[side].players.includes(a.id)),
    ...assets.picks.filter((a) => selection[side].picks.includes(a.id)),
  ];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{team.full_name}</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Trades</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist">
            {center.closed_reason ??
              `Trade players and ${center.draft_year} draft picks. Open through week ${center.deadline_week}; ` +
              "the other team says yes when it comes out ahead, and values positions it needs more."}
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="eyebrow">Trade with</span>
          <select className="field-input" value={partner?.id ?? ""}
            onChange={(e) => router.push(`/trades?partner=${e.target.value}`)}>
            {center.partners.map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name}{center.managed.includes(t.id) ? " (a member's team)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      {center.offers.length > 0 && <TradeOffers offers={center.offers} commissioner={commissioner} />}

      <section className="panel space-y-3 p-5" aria-label="Deal">
        <div className="grid gap-4 md:grid-cols-2">
          <DealSide title="You give" items={picked(center.mine, "send")} />
          <DealSide title="You get" items={picked(center.theirs, "receive")} />
        </div>
        <Meter evaluation={shown} />
        {shown && (
          <p className={`text-sm ${shown.acceptable ? "text-emerald-300" : "text-amber-200"}`} role="status"
            aria-label="Their answer">
            {shown.message}
          </p>
        )}
        {shown && shown.problems.length > 1 && (
          <ul className="list-disc pl-5 text-xs text-rose-300">
            {shown.problems.slice(1).map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        {status && !shown && <p className="text-sm text-emerald-300" role="status" aria-label="Trade result">{status}</p>}
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        {managed && (
          <label className="block space-y-1">
            <span className="eyebrow">
              {countering ? `Counter ${center.partner_manager}'s offer` : `Note to ${center.partner_manager}`} (optional)
            </span>
            <input className="field-input w-full" maxLength={200} value={note}
              onChange={(e) => setNote(e.target.value)} />
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" disabled={empty}
            onClick={() => { setSelection(EMPTY); setEvaluation(null); }}>
            Clear
          </button>
          <button type="button" className="btn btn-primary" disabled={empty || busy || !!center.closed_reason}
            onClick={propose}>
            {busy ? "Sending…" : managed ? (countering ? "Send counter-offer" : "Send offer") : "Propose trade"}
          </button>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <AssetPanel title={`${team.nickname} (you)`} assets={center.mine} side="send"
          selection={selection} onToggle={toggle} />
        {partner && (
          <AssetPanel title={partner.nickname} team={partner} assets={center.theirs} side="receive"
            selection={selection} onToggle={toggle} />
        )}
      </div>

      {center.history.length > 0 && (
        <section className="panel p-5" aria-label="Trade history">
          <h2 className="eyebrow mb-3">Your trades</h2>
          <ul className="space-y-2 text-sm">
            {center.history.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2">
                <TeamCrest team={t.partner} size={18} />
                <span className="text-mist">{t.partner.abbreviation}:</span>
                <span>sent {t.sent.map((i) => i.label).join(", ") || "nothing"}</span>
                <span className="text-mist">for</span>
                <span>{t.received.map((i) => i.label).join(", ") || "nothing"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function DealSide({ title, items }: { title: string; items: TradeAssetOut[] }) {
  const total = items.reduce((sum, a) => sum + a.value, 0);
  return (
    <div role="group" aria-label={title}>
      <h2 className="eyebrow mb-2">{title} {items.length > 0 && <span className="text-mist">· value {total.toFixed(0)}</span>}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-mist">Nothing yet — pick from the lists below.</p>
      ) : (
        <ul className="space-y-1 text-sm">{items.map((a) => <li key={`${a.kind}-${a.id}`}>{a.label}</li>)}</ul>
      )}
    </div>
  );
}

/** How close the deal is to a yes: their side's value against what they need (1.0). */
function Meter({ evaluation }: { evaluation: TradeEvaluation | null }) {
  const share = Math.min(1, (evaluation?.balance ?? 0) / 2);
  const color = !evaluation ? "bg-white/10" : evaluation.acceptable ? "bg-emerald-400"
    : evaluation.balance >= 0.85 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="space-y-1" aria-label="Trade meter" role="meter" aria-valuemin={0} aria-valuemax={2}
      aria-valuenow={evaluation?.balance ?? 0}>
      <div className="relative h-2 overflow-hidden rounded-full bg-white/5">
        <div className={`h-full ${color}`} style={{ width: `${share * 100}%` }} />
        <div className="absolute inset-y-0 left-1/2 w-px bg-chalk/60" />
      </div>
      <div className="flex justify-between text-[10px] uppercase tracking-wider text-mist">
        <span>They lose</span><span>Fair for them</span><span>They win</span>
      </div>
    </div>
  );
}

function AssetPanel({ title, team, assets, side, selection, onToggle }: {
  title: string; team?: TeamSummary; assets: TradeAssets; side: Side; selection: Selection;
  onToggle: (side: Side, kind: "players" | "picks", id: number) => void;
}) {
  return (
    <section className="panel p-5" aria-label={`${title} assets`}>
      <h2 className="eyebrow mb-3 flex items-center gap-2">{team && <TeamCrest team={team} size={18} />}{title}</h2>
      <h3 className="mb-1 text-xs uppercase tracking-wider text-mist">Draft picks</h3>
      <ul className="mb-4 space-y-1">
        {assets.picks.length === 0 && <li className="text-sm text-mist">No picks left to trade.</li>}
        {assets.picks.map((pick) => (
          <li key={pick.id}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" aria-label={`Trade ${pick.label}`}
                checked={selection[side].picks.includes(pick.id)}
                onChange={() => onToggle(side, "picks", pick.id)} />
              <span className="flex-1">{pick.label}</span>
              <span className="text-xs text-mist">~#{pick.projected_number}</span>
              <span className="w-10 text-right text-xs tabular-nums text-mist">{pick.value.toFixed(0)}</span>
            </label>
          </li>
        ))}
      </ul>
      <h3 className="mb-1 text-xs uppercase tracking-wider text-mist">Players</h3>
      <div className="max-h-[520px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-mist">
              <th className="w-6" />
              <th className="py-1 font-medium">Player</th>
              <th className="font-medium">Age</th>
              <th className="font-medium">OVR</th>
              <th className="text-right font-medium">Salary</th>
              <th className="text-right font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {assets.players.map((a) => a.player && (
              <tr key={a.id} className="border-t border-white/5">
                <td>
                  <input type="checkbox" aria-label={`Trade ${a.player.full_name}`}
                    checked={selection[side].players.includes(a.id)}
                    onChange={() => onToggle(side, "players", a.id)} />
                </td>
                <td className="py-1">
                  <Link href={`/players/${a.id}`} className="hover:text-gold">
                    <span className="mr-1.5 text-xs text-mist">{a.player.position}</span>
                    {a.player.full_name}
                  </Link>
                </td>
                <td className="tabular-nums text-mist">{a.player.age}</td>
                <td><OvrBadge value={a.player.overall} /></td>
                <td className="text-right tabular-nums text-mist">
                  {a.player.contract ? `${formatMoney(a.player.contract.salary)} · ${a.player.contract.end_year}` : "—"}
                </td>
                <td className="text-right tabular-nums">{a.value.toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
