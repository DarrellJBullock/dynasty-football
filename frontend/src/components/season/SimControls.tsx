"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { describeResult, gameLabel } from "@/lib/games";
import type {
  DraftResult, DraftUntil, FreeAgencyResult, FreeAgencyUntil, Game, Job, JobKind, Season,
  SimAheadResult, SimulateUntil, SimulationResult,
} from "@/lib/types";
import { JobProgress } from "./JobProgress";
import { useJob } from "./useJob";

/**
 * Season controls: sim the next week (or playoff round) or the rest of the regular season /
 * playoffs; shows the franchise's latest result. Once a champion is crowned, runs the
 * offseason into free agency, whose market days are played from here too. The long sims
 * run as background jobs (`useJob`) with a progress bar; a single week, market day or pick
 * is a plain request.
 */
export function SimControls({ season, teamId }: { season: Season; teamId: number }) {
  const router = useRouter();
  // A sim ahead can end in another phase than it started (free agency → the preseason
  // seasons later): its outcome lives here, above whichever phase's controls show.
  const [ahead, setAhead] = useState<Job | null>(null);
  function aheadDone(job: Job) {
    setAhead(job);
    router.refresh();
  }
  const controls = season.phase === "free_agency"
    ? <FreeAgencyControls season={season} onAheadDone={aheadDone} />
    : season.phase === "draft"
      ? <DraftControls season={season} onAheadDone={aheadDone} />
      : <SeasonControls season={season} teamId={teamId} onAheadDone={aheadDone} />;
  if (!ahead) return controls;
  return (
    <div className="space-y-2">
      {controls}
      <SimAheadOutcome job={ahead} />
    </div>
  );
}

/** Sim the next week (or round) or the rest of the season or playoffs; once a champion is
 * crowned, run the offseason. */
function SeasonControls({ season, teamId, onAheadDone }: {
  season: Season; teamId: number; onAheadDone: (job: Job) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<SimulateUntil | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [latest, setLatest] = useState<{ game: Game; label: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useJob(season.active_job, finished);
  const working = busy !== null || run.job !== null;

  async function simulateWeek() {
    setBusy("next_week");
    setError(null);
    setNotice(null);
    try {
      const result = await api.simulate(season.id, "next_week");
      const game = result.franchise_games.at(-1);
      // Eliminated or on a bye: nothing of ours this round.
      setLatest(game ? { game, label: `${gameLabel(game)}: ${describeResult(game, teamId)}` } : null);
      // Results change standings, records, brackets and schedules on every page.
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function startJob(kind: JobKind, seasons?: number) {
    setConfirming(false);
    setError(null);
    setNotice(null);
    try {
      await run.start(season.league_id, kind, seasons);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function finished(job: Job) {
    if (job.kind === "sim_seasons") {
      onAheadDone(job);
      return;
    }
    if (job.status === "failed") {
      setError(job.error ?? "The simulation failed.");
    } else if (job.status === "cancelled") {
      setLatest(null);
      setNotice(job.progress ? `Stopped after ${job.label}` : "Stopped");
    } else if (job.kind === "advance_offseason") {
      setLatest(null);
    } else {
      const result = job.result as SimulationResult;
      const game = result.franchise_games.at(-1);
      if (game) {
        setLatest({ game, label: `Simulated ${result.weeks_simulated} ` +
          `${job.kind === "sim_playoffs" ? "rounds" : "weeks"} · Last game: ${describeResult(game, teamId)}` });
      } else if (job.kind === "sim_playoffs") {
        setLatest(null);
      }
    }
    router.refresh();
  }

  const progress = run.job && <JobProgress job={run.job} onStop={run.cancel} />;

  if (season.champion) {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm" aria-label="Season status">
        <span className="flex items-center gap-2 rounded-md bg-gold/10 px-2.5 py-1 font-display font-semibold uppercase tracking-wide text-gold">
          <TeamCrest team={season.champion} size={20} />
          {season.year} champion: {season.champion.full_name}
        </span>
        {progress || (confirming ? (
          <>
            <button type="button" className="btn btn-primary" disabled={working}
              onClick={() => startJob("advance_offseason")}>
              Confirm: run the offseason
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" disabled={working}
            onClick={() => setConfirming(true)}>
            Start free agency
          </button>
        ))}
        {!progress && <SimAhead disabled={working} onStart={(n) => startJob("sim_seasons", n)} />}
        <Link href="/playoffs" className="text-gold hover:underline">Bracket →</Link>
        {latest && <ResultLink game={latest.game} label={latest.label} />}
        {notice && <span role="status" className="text-sm text-chalk">{notice}</span>}
        {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
      </div>
    );
  }

  const inPlayoffs = season.regular_season_complete;
  const nextLabel = inPlayoffs ? `Sim ${season.next_round ?? "next round"}` : `Sim week ${season.current_week}`;
  const restKind: JobKind = inPlayoffs ? "sim_playoffs" : "sim_regular_season";
  const restLabel = inPlayoffs ? "Sim rest of playoffs" : "Sim to end of season";
  const confirmLabel = inPlayoffs
    ? "Confirm: sim to a champion"
    : `Confirm: sim weeks ${season.current_week}–${season.weeks}`;

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Simulation">
      <button type="button" className="btn btn-primary" disabled={working} onClick={simulateWeek}>
        {busy === "next_week" ? "Simulating…" : nextLabel}
      </button>
      {progress || (confirming ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={working}
            onClick={() => startJob(restKind)}>
            {confirmLabel}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-ghost" disabled={working}
          onClick={() => setConfirming(true)}>
          {restLabel}
        </button>
      ))}
      {!progress && <SimAhead disabled={working} onStart={(n) => startJob("sim_seasons", n)} />}
      {inPlayoffs && <Link href="/playoffs" className="text-sm text-gold hover:underline">Bracket →</Link>}
      {latest && <ResultLink game={latest.game} label={latest.label} />}
      {notice && <span role="status" className="text-sm text-chalk">{notice}</span>}
      {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
    </div>
  );
}

/** Free agency: play the next market day, or the rest of the market (a background job). */
function FreeAgencyControls({ season, onAheadDone }: {
  season: Season; onAheadDone: (job: Job) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<FreeAgencyUntil | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useJob(season.active_job, finished);
  const working = busy !== null || run.job !== null;
  const day = season.free_agency_day ?? 1;

  function report(when: string, result: FreeAgencyResult) {
    const names = result.mine.map((s) => s.player.full_name);
    setSummary(`${when}: ${result.signings.length} signing(s) league-wide` +
      (names.length ? ` · you signed ${names.join(", ")}` : " · none of yours"));
  }

  async function playDay() {
    setBusy("next_day");
    setError(null);
    try {
      report(`Day ${day}`, await api.playFreeAgency(season.id, "next_day"));
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function finish(kind: JobKind = "finish_free_agency", seasons?: number) {
    setConfirming(false);
    setError(null);
    try {
      await run.start(season.league_id, kind, seasons);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function finished(job: Job) {
    if (job.kind === "sim_seasons") onAheadDone(job);
    else if (job.status === "failed") setError(job.error ?? "Free agency failed.");
    else if (job.status === "cancelled") setSummary(job.progress ? `Stopped after ${job.label}` : "Stopped");
    else report("Free agency", job.result as FreeAgencyResult);
    router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Free agency">
      <button type="button" className="btn btn-primary" disabled={working} onClick={playDay}>
        {busy === "next_day" ? "Playing…" : `Play free agency day ${day}`}
      </button>
      {run.job ? <JobProgress job={run.job} onStop={run.cancel} /> : confirming ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={working} onClick={() => finish()}>
            Confirm: finish free agency
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-ghost" disabled={working}
          onClick={() => setConfirming(true)}>
          Finish free agency
        </button>
      )}
      {!run.job && <SimAhead disabled={working} onStart={(n) => finish("sim_seasons", n)} />}
      <Link href="/free-agency" className="text-sm text-gold hover:underline">Free agents →</Link>
      {summary && <span role="status" className="text-sm text-chalk">{summary}</span>}
      {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
    </div>
  );
}

/** The draft: let AI teams pick until the franchise is up, or finish it (a background job). */
function DraftControls({ season, onAheadDone }: {
  season: Season; onAheadDone: (job: Job) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<DraftUntil | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useJob(season.active_job, finished);
  const working = busy !== null || run.job !== null;

  async function simToMyPick() {
    setBusy("my_pick");
    setError(null);
    try {
      const result = await api.playDraft(season.id, "my_pick");
      setSummary(result.season.phase === "draft"
        ? `${result.picks.length} pick(s) made · you're on the clock`
        : "The draft is complete");
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function finish(kind: JobKind = "finish_draft", seasons?: number) {
    setConfirming(false);
    setError(null);
    try {
      await run.start(season.league_id, kind, seasons);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function finished(job: Job) {
    if (job.kind === "sim_seasons") onAheadDone(job);
    else if (job.status === "failed") setError(job.error ?? "The draft failed.");
    else if (job.status === "done" && (job.result as DraftResult).season.phase !== "draft") {
      setSummary("The draft is complete");
    }
    router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Draft">
      <button type="button" className="btn btn-primary" disabled={working} onClick={simToMyPick}>
        {busy === "my_pick" ? "Picking…" : "Sim to my pick"}
      </button>
      {run.job ? <JobProgress job={run.job} onStop={run.cancel} /> : confirming ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={working} onClick={() => finish()}>
            Confirm: finish the draft (auto-pick for me)
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-ghost" disabled={working}
          onClick={() => setConfirming(true)}>
          Finish draft
        </button>
      )}
      {!run.job && <SimAhead disabled={working} onStart={(n) => finish("sim_seasons", n)} />}
      <Link href="/draft" className="text-sm text-gold hover:underline">Draft board →</Link>
      {summary && <span role="status" className="text-sm text-chalk">{summary}</span>}
      {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
    </div>
  );
}

/** Sim ahead 1–10 seasons, with the franchise on autopilot through each offseason. */
function SimAhead({ disabled, onStart }: { disabled: boolean; onStart: (seasons: number) => void }) {
  const [open, setOpen] = useState(false);
  const [seasons, setSeasons] = useState(3);
  if (!open) {
    return (
      <button type="button" className="btn btn-ghost" disabled={disabled} onClick={() => setOpen(true)}>
        Sim ahead…
      </button>
    );
  }
  return (
    <span role="group" aria-label="Sim ahead" className="flex flex-wrap items-center gap-2 text-sm">
      <label className="flex items-center gap-1.5">
        Seasons
        <select className="field-input w-auto py-1" value={seasons}
          onChange={(e) => setSeasons(Number(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <button type="button" className="btn btn-primary" disabled={disabled}
        onClick={() => { setOpen(false); onStart(seasons); }}>
        Confirm: sim ahead {seasons} season{seasons === 1 ? "" : "s"}
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
      <span className="text-xs text-mist">The AI runs your team through each offseason.</span>
    </span>
  );
}

/** How a sim ahead ended: a link to its Dynasty report, where it stopped, or why it failed. */
function SimAheadOutcome({ job }: { job: Job }) {
  if (job.status === "failed") {
    return <p role="alert" className="text-sm text-rose-300">{job.error ?? "The sim ahead failed."}</p>;
  }
  if (job.status === "cancelled") {
    return <p role="status" className="text-sm text-chalk">{job.progress ? `Stopped after ${job.label}` : "Stopped"}</p>;
  }
  const result = job.result as SimAheadResult;
  return (
    <Link href={`/dynasty?from=${result.from_year}&to=${result.to_year}`} role="status"
      className="block text-sm text-gold underline-offset-4 hover:underline">
      Simmed {result.seasons} season{result.seasons === 1 ? "" : "s"} · Dynasty report,{" "}
      {result.from_year === result.to_year ? result.from_year : `${result.from_year}–${result.to_year}`} →
    </Link>
  );
}

function ResultLink({ game, label }: { game: Game; label: string }) {
  return (
    <Link href={`/games/${game.id}`} role="status" className="text-sm text-chalk underline-offset-4 hover:underline">
      {label} →
    </Link>
  );
}
