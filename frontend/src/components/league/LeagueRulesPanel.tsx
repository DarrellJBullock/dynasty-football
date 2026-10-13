"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { LeagueRules, LeagueRulesIn } from "@/lib/types";

const AUTOMATIC = "auto";

function seedsText(rules: LeagueRules): string {
  const byes = rules.byes === 0 ? "no byes" : `${rules.byes} bye${rules.byes === 1 ? "" : "s"}`;
  return `${rules.seeds} per conference, ${byes}${rules.playoff_seeds === null ? " (by conference size)" : ""}`;
}

/**
 * The league's rules for everyone to see; the commissioner changes them between seasons
 * (after the champion is crowned, before week 1), so a season is never played under two
 * sets of rules.
 */
export function LeagueRulesPanel({ leagueId, initial, commissioner }: {
  leagueId: number;
  initial: LeagueRules;
  commissioner: boolean;
}) {
  const [rules, setRules] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => toForm(initial));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toForm(r: LeagueRules) {
    return {
      roster_max: String(r.roster_max), salary_cap: (r.salary_cap / 1_000_000).toFixed(1),
      cap_growth_pct: String(r.cap_growth_pct),
      playoff_seeds: r.playoff_seeds === null ? AUTOMATIC : String(r.playoff_seeds),
      season_weeks: String(r.season_weeks),
    };
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const change: LeagueRulesIn = {};
    const roster = Number(form.roster_max);
    if (roster !== rules.roster_max) change.roster_max = roster;
    const cap = Math.round(Number(form.salary_cap) * 1_000_000);
    if (cap !== rules.salary_cap) change.salary_cap = cap;
    const growth = Number(form.cap_growth_pct);
    if (growth !== rules.cap_growth_pct) change.cap_growth_pct = growth;
    const seeds = form.playoff_seeds === AUTOMATIC ? null : Number(form.playoff_seeds);
    if (seeds !== rules.playoff_seeds) change.playoff_seeds = seeds;
    const weeks = Number(form.season_weeks);
    if (weeks !== rules.season_weeks) change.season_weeks = weeks;
    if (Object.keys(change).length === 0) {
      setEditing(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await api.updateRules(leagueId, change);
      setRules(saved);
      setForm(toForm(saved));
      setEditing(false);
      setNotice("Saved: the change is in the League log.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const set = (key: keyof ReturnType<typeof toForm>) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: e.target.value });

  return (
    <section className="panel space-y-3 p-5" aria-label="League rules">
      <h2 className="eyebrow">League rules</h2>
      {editing ? (
        <form onSubmit={save} className="space-y-3 text-sm">
          <label className="block text-xs text-mist">
            Roster size (45–60)
            <input className="input mt-1 w-full" type="number" min={45} max={60} required
              value={form.roster_max} onChange={set("roster_max")} />
          </label>
          <label className="block text-xs text-mist">
            Salary cap ($M)
            <input className="input mt-1 w-full" type="number" min={50} max={1000} step={0.1} required
              value={form.salary_cap} onChange={set("salary_cap")} />
          </label>
          <label className="block text-xs text-mist">
            Cap growth each season (%)
            <input className="input mt-1 w-full" type="number" min={0} max={10} step={0.5} required
              value={form.cap_growth_pct} onChange={set("cap_growth_pct")} />
          </label>
          <label className="block text-xs text-mist">
            Playoff seeds per conference
            <select className="input mt-1 w-full" value={form.playoff_seeds} onChange={set("playoff_seeds")}>
              <option value={AUTOMATIC}>By conference size</option>
              {rules.seed_choices.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="block text-xs text-mist">
            Regular season (weeks)
            <input className="input mt-1 w-full" type="number" min={1} max={rules.max_weeks} required
              value={form.season_weeks} onChange={set("season_weeks")} />
          </label>
          <p className="text-xs text-mist">
            A new length draws this season&apos;s schedule again if no game has been played;
            in the offseason it&apos;s next season&apos;s.
          </p>
          <div className="flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Saving…" : "Save rules"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => {
              setEditing(false);
              setForm(toForm(rules));
            }}>Cancel</button>
          </div>
        </form>
      ) : (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-mist">Roster size</dt><dd>{rules.roster_max} players</dd>
            <dt className="text-mist">Salary cap</dt><dd>{formatMoney(rules.salary_cap)}</dd>
            <dt className="text-mist">Cap growth</dt>
            <dd>{rules.cap_growth_pct === 0 ? "None" : `${rules.cap_growth_pct}% a season`}</dd>
            <dt className="text-mist">Playoffs</dt><dd>{seedsText(rules)}</dd>
            <dt className="text-mist">Season</dt><dd>{rules.season_weeks} weeks</dd>
          </dl>
          {commissioner && (rules.locked_reason ? (
            <p className="text-xs text-mist">{rules.locked_reason}</p>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={() => setEditing(true)}>Change the rules</button>
          ))}
        </>
      )}
      {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
    </section>
  );
}
