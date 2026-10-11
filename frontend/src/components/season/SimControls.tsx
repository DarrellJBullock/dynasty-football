"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { describeResult, gameLabel } from "@/lib/games";
import type { Game, Season, SimulateUntil } from "@/lib/types";

/**
 * Season controls: sim the next week (or playoff round) or the rest of the regular season /
 * playoffs; shows the franchise's latest result. Once a champion is crowned, starts the next
 * season (aging, development, retirements, contracts, rookies happen in between).
 */
export function SimControls({ season, teamId }: { season: Season; teamId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState<SimulateUntil | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [latest, setLatest] = useState<{ game: Game; label: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);

  async function simulate(until: SimulateUntil) {
    setBusy(until);
    setConfirming(false);
    setError(null);
    try {
      const result = await api.simulate(season.id, until);
      const game = result.franchise_games.at(-1);
      if (game) {
        const label = until === "next_week"
          ? `${gameLabel(game)}: ${describeResult(game, teamId)}`
          : `Simulated ${result.weeks_simulated} ${until === "end_of_playoffs" ? "rounds" : "weeks"} · ` +
            `Last game: ${describeResult(game, teamId)}`;
        setLatest({ game, label });
      } else if (until !== "end_of_regular_season") {
        setLatest(null); // eliminated or on a bye: nothing of ours this round
      }
      // Results change standings, records, brackets and schedules on every page.
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function advance() {
    setAdvancing(true);
    setConfirming(false);
    setError(null);
    try {
      await api.advance(season.id);
      setLatest(null);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdvancing(false);
    }
  }

  if (season.champion) {
    const next = season.year + 1;
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm" aria-label="Season status">
        <span className="flex items-center gap-2 rounded-md bg-gold/10 px-2.5 py-1 font-display font-semibold uppercase tracking-wide text-gold">
          <TeamCrest team={season.champion} size={20} />
          {season.year} champion: {season.champion.full_name}
        </span>
        {confirming ? (
          <>
            <button type="button" className="btn btn-primary" disabled={advancing} onClick={advance}>
              Confirm: run the offseason
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" disabled={advancing}
            onClick={() => setConfirming(true)}>
            {advancing ? "Running offseason…" : `Start ${next} season`}
          </button>
        )}
        <Link href="/playoffs" className="text-gold hover:underline">Bracket →</Link>
        {latest && <ResultLink game={latest.game} label={latest.label} />}
        {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
      </div>
    );
  }

  const inPlayoffs = season.regular_season_complete;
  const nextLabel = inPlayoffs ? `Sim ${season.next_round ?? "next round"}` : `Sim week ${season.current_week}`;
  const restUntil: SimulateUntil = inPlayoffs ? "end_of_playoffs" : "end_of_regular_season";
  const restLabel = inPlayoffs ? "Sim rest of playoffs" : "Sim to end of season";
  const confirmLabel = inPlayoffs
    ? "Confirm: sim to a champion"
    : `Confirm: sim weeks ${season.current_week}–${season.weeks}`;

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Simulation">
      <button type="button" className="btn btn-primary" disabled={busy !== null}
        onClick={() => simulate("next_week")}>
        {busy === "next_week" ? "Simulating…" : nextLabel}
      </button>
      {confirming ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={busy !== null}
            onClick={() => simulate(restUntil)}>
            {confirmLabel}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-ghost" disabled={busy !== null}
          onClick={() => setConfirming(true)}>
          {busy === restUntil ? "Simulating…" : restLabel}
        </button>
      )}
      {inPlayoffs && <Link href="/playoffs" className="text-sm text-gold hover:underline">Bracket →</Link>}
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
