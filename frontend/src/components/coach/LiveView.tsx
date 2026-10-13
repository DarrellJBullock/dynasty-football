"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { Game, GamePlayback, LiveState, Playbook } from "@/lib/types";
import { type CoachActions, type CoachViewState, CoachView, POLL_MS } from "./CoachView";

/** The call clocks a manager can offer (seconds; null: no clock). */
export const CLOCKS: { value: number | null; label: string }[] = [
  { value: null, label: "No clock" },
  { value: 120, label: "2 minutes a call" },
  { value: 600, label: "10 minutes a call" },
  { value: 3600, label: "An hour a call" },
  { value: 86400, label: "A day a call" },
];

function clockLabel(seconds: number | null): string {
  return CLOCKS.find((c) => c.value === seconds)?.label.toLowerCase() ?? `${seconds} seconds a call`;
}

/** A live state as the coaching screen sees it (only for one of the two coaches). */
function forCoach(live: LiveState): CoachViewState {
  return { ...live, side: live.side ?? "home", team: live.team ?? live.game.home };
}

/**
 * Playing head-to-head: offer to play the week's game against another manager live, say
 * yes or no to an offer, then coach it together (each snap waits on both calls).
 */
export function LiveView({ game, playbook, initialLive, initialPlayback }: {
  game: Game;
  playbook: Playbook;
  initialLive: LiveState | null;
  initialPlayback: GamePlayback | null;
}) {
  const [live, setLive] = useState(initialLive);
  const [playback, setPlayback] = useState(initialPlayback);
  const [clock, setClock] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(request: () => Promise<LiveState>) {
    setBusy(true);
    setError(null);
    try {
      const next = await request();
      if (next.status !== "proposed" && next.status !== "declined") setPlayback(await api.playback(game.id));
      setLive(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // An offer we made: watch for the answer.
  const awaitingAnswer = live?.status === "proposed" && live.proposed_by_you;
  useEffect(() => {
    if (!awaitingAnswer) return;
    const timer = setInterval(async () => {
      try {
        const next = await api.liveGame(game.id);
        if (next.status !== "proposed") {
          if (next.status !== "declined") setPlayback(await api.playback(game.id));
          setLive(next);
        }
      } catch {
        // (try again next time)
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [awaitingAnswer, game.id]);

  const coaching = live && live.side && !["proposed", "declined"].includes(live.status);
  if (coaching) {
    const actions: CoachActions = {
      call: async (c) => forCoach(await api.liveCall(game.id, c)),
      auto: async (scope) => forCoach(await api.liveAuto(game.id, scope)),
      load: async () => forCoach(await api.liveGame(game.id)),
    };
    return <CoachView game={game} playbook={playbook} initialState={forCoach(live)}
      initialPlayback={playback} actions={actions} mode="Live" />;
  }

  const other = live?.side === "home" ? "away" : "home";
  return (
    <div className="mx-auto max-w-3xl">
      <section className="panel space-y-5 p-6 text-center" aria-label="Play it live">
        <p className="eyebrow">{game.round_name ?? `Week ${game.week}`} · Head-to-head</p>
        <div className="flex items-center justify-center gap-6">
          <TeamCrest team={game.away} size={56} />
          <span className="font-display text-lg text-mist">at</span>
          <TeamCrest team={game.home} size={56} />
        </div>
        <h1 className="font-display text-2xl font-bold uppercase">
          {game.away.full_name} at {game.home.full_name}
        </h1>

        {live === null ? (
          game.status === "final" ? (
            <p className="text-sm text-mist">
              This game has been played.{" "}
              <Link href={`/games/${game.id}`} className="text-gold hover:underline">Box score</Link>
            </p>
          ) : (
            <>
              <p className="text-sm text-mist">
                Both teams are managed by people, so this game is simulated from both game
                plans, unless you both agree to play it live: each of you calls your own side,
                every snap, at the same time and blind to the other&apos;s call.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <label className="flex items-center gap-2 text-sm">
                  Call clock
                  <select className="input w-auto" value={clock ?? ""}
                    onChange={(e) => setClock(e.target.value ? Number(e.target.value) : null)}>
                    {CLOCKS.map((c) => (
                      <option key={c.label} value={c.value ?? ""}>{c.label}</option>
                    ))}
                  </select>
                </label>
                <button type="button" className="btn btn-primary" disabled={busy}
                  onClick={() => run(() => api.offerLive(game.id, clock))}>
                  Offer to play it live
                </button>
              </div>
              <p className="text-xs text-mist">
                With a call clock, the AI calls from your game plan for whoever runs out of
                time. Unfinished when the week is simulated, the AI finishes it for both of you.
              </p>
            </>
          )
        ) : live.status === "declined" ? (
          <p className="text-sm text-mist">
            The offer to play it live was declined, so the game will be simulated from both
            game plans with the rest of the week.
          </p>
        ) : live.status === "proposed" && live.proposed_by_you ? (
          <p className="text-sm text-mist" aria-live="polite">
            You offered to play it live ({clockLabel(live.clock_seconds)}). Waiting for{" "}
            {live.managers[other]} to say yes; this page updates by itself.
          </p>
        ) : live.status === "proposed" && live.side ? (
          <>
            <p className="text-sm">
              {live.managers[other]} wants to play this game live with you
              ({clockLabel(live.clock_seconds)}).
            </p>
            <div className="flex justify-center gap-3">
              <button type="button" className="btn btn-primary" disabled={busy}
                onClick={() => run(() => api.acceptLive(game.id))}>Play it live</button>
              <button type="button" className="btn btn-ghost" disabled={busy}
                onClick={() => run(() => api.declineLive(game.id))}>No thanks</button>
            </div>
          </>
        ) : (
          <p className="text-sm text-mist">
            {live.managers.away} and {live.managers.home} are{" "}
            {live.status === "proposed" ? "deciding whether to play this game live" : "playing this game live"}.{" "}
            <Link href={`/games/${game.id}/watch`} className="text-gold hover:underline">Watch it</Link>
          </p>
        )}
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      </section>
    </div>
  );
}
