"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { TradeOffer, TradeOfferItem, TradeOfferStatus } from "@/lib/types";

const when = new Intl.DateTimeFormat("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" });

const STATUS: Record<TradeOfferStatus, string> = {
  pending: "Waiting for an answer", accepted: "Done", rejected: "Rejected", withdrawn: "Withdrawn",
  countered: "Countered", expired: "Expired", invalid: "No longer valid",
  review: "Accepted · in the veto window", vetoed: "Vetoed",
};

/** What each side of an offer gives, from the viewer's side when it's theirs. */
export function offerSides(offer: TradeOffer): { title: string; items: TradeOfferItem[] }[] {
  if (offer.direction === "incoming") {
    return [{ title: "You get", items: offer.gives }, { title: "You give", items: offer.gets }];
  }
  if (offer.direction === "outgoing") {
    return [{ title: "You give", items: offer.gives }, { title: "You get", items: offer.gets }];
  }
  return [{ title: `${offer.from_team.nickname} give`, items: offer.gives },
    { title: `${offer.to_team.nickname} give`, items: offer.gets }];
}

/**
 * Trade offers between managers: answer the ones made to you (accept, reject, or counter),
 * withdraw your own, and, as commissioner, veto or approve trades in the veto window.
 */
export function TradeOffers({ offers, commissioner }: { offers: TradeOffer[]; commissioner: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function act(offer: TradeOffer, action: () => Promise<TradeOffer>) {
    setBusy(offer.id);
    setError(null);
    setNotice(null);
    try {
      const result = await action();
      setNotice(`${offer.from_team.nickname} ↔ ${offer.to_team.nickname}: ${STATUS[result.status].toLowerCase()}.`);
      router.refresh(); // (rosters and the other offers change)
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel space-y-3 p-5" aria-label="Trade offers">
      <h2 className="eyebrow">Offers between managers</h2>
      {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <ul className="divide-y divide-white/5">
        {offers.map((offer) => {
          const open = offer.status === "pending";
          const working = busy === offer.id;
          return (
            <li key={offer.id} aria-label={`Offer ${offer.from_team.abbreviation} to ${offer.to_team.abbreviation}`}
              className="space-y-2 py-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <TeamCrest team={offer.from_team} size={18} />
                <span className="font-semibold">{offer.from_manager}</span>
                <span className="text-mist">({offer.from_team.abbreviation}) →</span>
                <TeamCrest team={offer.to_team} size={18} />
                <span className="font-semibold">{offer.to_manager}</span>
                <span className="text-mist">({offer.to_team.abbreviation})</span>
                <span className={`ml-auto rounded-full px-2 py-0.5 text-xs ${
                  open || offer.status === "review" ? "bg-gold/10 text-gold" : "bg-white/5 text-mist"}`}>
                  {STATUS[offer.status]}
                </span>
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                {offerSides(offer).map((side) => (
                  <div key={side.title}>
                    <span className="eyebrow mr-2">{side.title}</span>
                    {side.items.map((i) => i.label).join(", ") || "nothing"}
                  </div>
                ))}
              </div>
              {offer.note && <p className="text-sm italic text-mist">“{offer.note}”</p>}
              {offer.reason && <p className="text-xs text-mist">{offer.reason}</p>}
              <div className="flex flex-wrap items-center gap-2">
                {open && <span className="text-xs text-mist">Expires {when.format(new Date(offer.expires_at))}</span>}
                {offer.status === "review" && offer.review_ends_at && (
                  <span className="text-xs text-mist">Goes through {when.format(new Date(offer.review_ends_at))}</span>
                )}
                <span className="ml-auto flex flex-wrap gap-2">
                  {open && offer.direction === "incoming" && (
                    <>
                      <button type="button" className="btn btn-primary" disabled={working}
                        onClick={() => act(offer, () => api.acceptOffer(offer.id))}>Accept</button>
                      <button type="button" className="btn btn-ghost" disabled={working}
                        onClick={() => router.push(`/trades?partner=${offer.from_team.id}&counter=${offer.id}`)}>
                        Counter…
                      </button>
                      <button type="button" className="btn btn-ghost" disabled={working}
                        onClick={() => act(offer, () => api.rejectOffer(offer.id))}>Reject</button>
                    </>
                  )}
                  {open && offer.direction === "outgoing" && (
                    <button type="button" className="btn btn-ghost" disabled={working}
                      onClick={() => act(offer, () => api.withdrawTradeOffer(offer.id))}>Withdraw</button>
                  )}
                  {offer.status === "review" && commissioner && (
                    <>
                      <button type="button" className="btn btn-ghost" disabled={working}
                        onClick={() => act(offer, () => api.approveOffer(offer.id))}>Approve now</button>
                      <button type="button" className="btn btn-danger" disabled={working}
                        onClick={() => act(offer, () => api.vetoOffer(offer.id))}>Veto</button>
                    </>
                  )}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
