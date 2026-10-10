"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { describeResult } from "@/lib/games";
import type { Game, Season, SimulateUntil } from "@/lib/types";

/** "Sim week N" / "Sim to end of season", with the franchise's latest result. */
export function SimControls({ season, teamId }: { season: Season; teamId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState<SimulateUntil | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [latest, setLatest] = useState<{ game: Game; label: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function simulate(until: SimulateUntil) {
    setBusy(until);
    setConfirming(false);
    setError(null);
    try {
      const result = await api.simulate(season.id, until);
      const game = result.franchise_games.at(-1);
      if (game) {
        const label = until === "next_week"
          ? `Week ${game.week}: ${describeResult(game, teamId)}`
          : `Simulated ${result.weeks_simulated} weeks · Last game: ${describeResult(game, teamId)}`;
        setLatest({ game, label });
      }
      // Results change standings, records and schedules on every page.
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (season.regular_season_complete) {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm" aria-label="Season status">
        <span className="rounded-md bg-gold/10 px-2.5 py-1 font-display font-semibold uppercase tracking-wide text-gold">
          Regular season complete
        </span>
        <span className="text-mist">Playoffs arrive in a future update.</span>
        {latest && <ResultLink game={latest.game} label={latest.label} />}
      </div>
    );
  }

  const week = season.current_week;
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Simulation">
      <button type="button" className="btn btn-primary" disabled={busy !== null}
        onClick={() => simulate("next_week")}>
        {busy === "next_week" ? `Simulating week ${week}…` : `Sim week ${week}`}
      </button>
      {confirming ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={busy !== null}
            onClick={() => simulate("end_of_regular_season")}>
            Confirm: sim weeks {week}–{season.weeks}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-ghost" disabled={busy !== null}
          onClick={() => setConfirming(true)}>
          {busy === "end_of_regular_season" ? "Simulating season…" : "Sim to end of season"}
        </button>
      )}
      {latest && <ResultLink game={latest.game} label={latest.label} />}
      {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
    </div>
  );
}

function ResultLink({ game, label }: { game: Game; label: string }) {
  return (
    <Link href={`/games/${game.id}`} role="status" className="text-sm text-chalk underline-offset-4 hover:underline">
      {label} →
    </Link>
  );
}
