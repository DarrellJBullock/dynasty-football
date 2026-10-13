"use client";

import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { GmCareer, GmJob } from "@/lib/types";

const SITUATION = { contender: "Contender", middle: "Middle of the league", rebuilding: "Rebuilding" };

function record(w: number, l: number, t: number): string {
  return `${w}-${l}${t ? `-${t}` : ""}`;
}

/**
 * A member's career as a general manager in this league: every team, its seasons and how it
 * ended. Fired, they choose their next job here (their old team goes to the AI).
 */
export function CareerView({ initial }: { initial: GmCareer }) {
  const career = initial;
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function take(job: GmJob) {
    setBusy(true);
    setError(null);
    try {
      await api.takeJob(job.team.id);
      hardNavigate("/");  // (a new team: every page starts afresh)
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader eyebrow={`General manager · ${career.name}`} title="Career">
        <TeamCrest team={career.team} size={40} />
      </PageHeader>

      {career.fired && (
        <section className="panel mb-6 space-y-4 border-rose-400/30 p-5" aria-label="Open jobs">
          <div>
            <h2 className="font-display text-xl font-bold uppercase">You&apos;ve been fired by the {career.team.full_name}</h2>
            <p className="text-sm text-mist">
              Choose your next job before the offseason begins. You keep your career record;
              the {career.team.full_name} go to the AI.
            </p>
          </div>
          <ul className="grid gap-4 md:grid-cols-3">
            {career.open_jobs.map((job) => (
              <li key={job.team.id} className="space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-center gap-3">
                  <TeamCrest team={job.team} size={32} />
                  <h3 className="font-semibold">{job.team.full_name}</h3>
                </div>
                <p className="text-xs text-mist">{job.why}</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                  <dt className="text-mist">Owner</dt><dd>{job.owner} {job.wants} (patience {job.patience} of 5)</dd>
                  <dt className="text-mist">Roster</dt><dd>{job.rating} overall · {SITUATION[job.situation]}</dd>
                  <dt className="text-mist">Last season</dt><dd>{job.last_season ?? "—"}</dd>
                  <dt className="text-mist">Market</dt><dd className="capitalize">{job.market} · fans {job.fan_mood}</dd>
                </dl>
                {confirming === job.team.id ? (
                  <div className="flex gap-2">
                    <button type="button" className="btn btn-primary px-3 py-1 text-xs" disabled={busy}
                      onClick={() => take(job)}>Confirm: take this job</button>
                    <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
                      onClick={() => setConfirming(null)}>Cancel</button>
                  </div>
                ) : (
                  <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
                    aria-label={`Take the ${job.team.full_name} job`}
                    onClick={() => setConfirming(job.team.id)}>Take this job</button>
                )}
              </li>
            ))}
          </ul>
          {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        </section>
      )}

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4" role="group" aria-label="Career totals">
        {[
          ["Record", record(career.wins, career.losses, career.ties)],
          ["Playoff seasons", String(career.playoffs)],
          ["Titles", String(career.titles)],
          ["Times fired", String(career.firings)],
        ].map(([label, value]) => (
          <section key={label} className="panel p-5" aria-label={label}>
            <h2 className="eyebrow">{label}</h2>
            <p className="stat-number mt-2 text-3xl">{value}</p>
          </section>
        ))}
      </div>

      <Panel title="Teams" className="mt-6">
        <table className="w-full text-sm">
          <caption className="sr-only">Every team you&apos;ve run</caption>
          <thead>
            <tr className="text-left text-xs text-mist">
              <th scope="col" className="py-1 font-normal">Team</th>
              <th scope="col" className="py-1 font-normal">Seasons</th>
              <th scope="col" className="py-1 font-normal">Record</th>
              <th scope="col" className="py-1 font-normal">Playoffs</th>
              <th scope="col" className="py-1 font-normal">Titles</th>
              <th scope="col" className="py-1 font-normal">How it ended</th>
            </tr>
          </thead>
          <tbody>
            {career.stints.map((s) => (
              <tr key={`${s.team.id}-${s.from_year}`} className="border-t border-white/[0.04]">
                <th scope="row" className="py-1 text-left font-normal">
                  <span className="flex items-center gap-2"><TeamCrest team={s.team} size={18} />{s.team.full_name}</span>
                </th>
                <td className="py-1 tabular-nums">
                  {s.from_year}–{s.to_year ?? "now"} ({s.seasons})
                </td>
                <td className="py-1 tabular-nums">{record(s.wins, s.losses, s.ties)}</td>
                <td className="py-1 tabular-nums">{s.playoffs}</td>
                <td className="py-1 tabular-nums">{s.titles}</td>
                <td className="py-1">{s.ended === "fired" ? "Fired" : s.to_year === null ? "Still there" : "Moved on"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
