"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import type { Turn } from "@/lib/types";

export const DRAFT_CLOCKS = [2, 5, 15, 60, 240, 720, 1440];

export function clockLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes`;
  if (minutes < 1440) return `${minutes / 60} hour${minutes === 60 ? "" : "s"}`;
  return "1 day";
}

/** "21:00" in the viewer's time zone ↔ minutes after midnight UTC. */
export function localToUtcMinutes(time: string, offsetMinutes: number): number {
  const [h, m] = time.split(":").map(Number);
  return (((h * 60 + m + offsetMinutes) % 1440) + 1440) % 1440;
}

export function utcMinutesToLocal(minutes: number, offsetMinutes: number): string {
  const local = (((minutes - offsetMinutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(local / 60)).padStart(2, "0")}:${String(local % 60).padStart(2, "0")}`;
}

/** The commissioner's league settings: the draft clock, and the daily advance. */
export function LeagueSettingsPanel({ leagueId }: { leagueId: number }) {
  const [turn, setTurn] = useState<Turn | null>(null);
  const [time, setTime] = useState("21:00");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const offset = new Date().getTimezoneOffset(); // (minutes behind UTC)

  useEffect(() => {
    let live = true;
    api.turn(leagueId).then((found) => {
      if (!live) return;
      setTurn(found);
      if (found.advance_minute_utc !== null) setTime(utcMinutesToLocal(found.advance_minute_utc, offset));
    }, (e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [leagueId, offset]);

  async function save(change: Parameters<typeof api.updateLeagueSettings>[1], message: string) {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      setTurn(await api.updateLeagueSettings(leagueId, change));
      setSaved(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!turn) return null;
  const daily = turn.advance_minute_utc !== null;

  return (
    <Panel title="League settings">
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="draft-clock" className="eyebrow block">Draft clock</label>
          <select id="draft-clock" className="field-input w-full" value={turn.draft_clock_minutes}
            disabled={busy} aria-describedby="draft-clock-hint"
            onChange={(e) => save({ draft_clock_minutes: Number(e.target.value) }, "Draft clock saved.")}>
            {DRAFT_CLOCKS.map((m) => <option key={m} value={m}>{clockLabel(m)}</option>)}
          </select>
          <span id="draft-clock-hint" className="block text-xs text-mist">
            How long a manager has to pick; then it&apos;s made by need.
          </span>
        </div>
        <div className="space-y-1">
          <label htmlFor="staff-budget" className="eyebrow block">Staff budget</label>
          <select id="staff-budget" className="field-input w-full" value={turn.staff_budget ?? 20_000_000}
            disabled={busy} aria-describedby="staff-budget-hint"
            onChange={(e) => save({ staff_budget: Number(e.target.value) }, "Staff budget saved.")}>
            {[10, 15, 20, 25, 30, 40].map((m) => <option key={m} value={m * 1_000_000}>${m}M a season</option>)}
          </select>
          <span id="staff-budget-hint" className="block text-xs text-mist">
            What each team may spend on coaches, a scout and a trainer (not the player salary cap).
          </span>
        </div>
        <div className="space-y-1">
          <label htmlFor="trade-review" className="eyebrow block">Trade veto window</label>
          <select id="trade-review" className="field-input w-full" value={turn.trade_review_hours}
            disabled={busy} aria-describedby="trade-review-hint"
            onChange={(e) => save({ trade_review_hours: Number(e.target.value) }, "Veto window saved.")}>
            {[0, 24, 48].map((h) => <option key={h} value={h}>{h ? `${h} hours` : "None"}</option>)}
          </select>
          <span id="trade-review-hint" className="block text-xs text-mist">
            Trades between managers wait this long for your veto before they go through.
          </span>
        </div>
        <div className="space-y-1">
          <label className="block space-y-1">
            <span className="eyebrow">Advance every day at (your time)</span>
            <input className="field-input w-full" type="time" value={time} disabled={busy}
              onChange={(e) => setTime(e.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2 pt-1">
            <button type="button" className="btn btn-primary" disabled={busy || !time}
              onClick={() => save({ advance_minute_utc: localToUtcMinutes(time, offset) },
                `The league advances every day at ${time}.`)}>
              {daily ? "Change time" : "Advance daily"}
            </button>
            {daily && (
              <button type="button" className="btn btn-ghost" disabled={busy}
                onClick={() => save({ advance_minute_utc: null }, "The daily advance is off.")}>
                Turn off
              </button>
            )}
          </div>
          <span className="block text-xs text-mist">
            {daily ? "On: the league plays the next step at this time, ready or not." :
              "Off: you advance the league yourself."}
          </span>
        </div>
      </div>
      {saved && <p role="status" className="mt-3 text-sm text-emerald-300">{saved}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
    </Panel>
  );
}
