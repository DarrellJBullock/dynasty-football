"use client";

import { useEffect, useState } from "react";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { POSITIONS, type PlayerSummary, type Position } from "@/lib/types";
import { Dialog } from "@/components/ui/Dialog";

export function FreeAgentsDialog({
  leagueId,
  rosterFull,
  onSign,
  onClose,
}: {
  leagueId: number;
  rosterFull: boolean;
  onSign: (player: PlayerSummary) => Promise<void>;
  onClose: () => void;
}) {
  const [players, setPlayers] = useState<PlayerSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState<Position | "ALL">("ALL");
  const [signingId, setSigningId] = useState<number | null>(null);

  useEffect(() => {
    api.freeAgents(leagueId).then(setPlayers).catch((e: Error) => setError(e.message));
  }, [leagueId]);

  async function sign(player: PlayerSummary) {
    setSigningId(player.id);
    setError(null);
    try {
      await onSign(player);
      setPlayers((current) => current?.filter((p) => p.id !== player.id) ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSigningId(null);
    }
  }

  const visible = players?.filter((p) => position === "ALL" || p.position === position) ?? [];

  return (
    <Dialog title="Free agents" onClose={onClose}>
      {rosterFull && (
        <p className="mb-4 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-sm text-amber-200">
          Your roster is full. Release a player before signing a free agent.
        </p>
      )}
      <div className="mb-4 flex items-center gap-3">
        <label htmlFor="fa-position" className="text-xs text-mist">
          Position
        </label>
        <select
          id="fa-position"
          className="field-input w-32"
          value={position}
          onChange={(e) => setPosition(e.target.value as Position | "ALL")}
        >
          <option value="ALL">All</option>
          {POSITIONS.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        {players && <span className="text-xs text-mist">{visible.length} available</span>}
      </div>
      {error && (
        <p role="alert" className="mb-3 text-sm text-rose-300">
          {error}
        </p>
      )}
      {!players && !error && <p className="text-sm text-mist">Loading free agents…</p>}
      <ul className="divide-y divide-white/5">
        {visible.map((player) => (
          <li key={player.id} className="flex items-center gap-3 py-2.5">
            <OvrBadge value={player.overall} size="md" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{player.full_name}</div>
              <div className="text-xs text-mist">
                {player.position} · Age {player.age} · POT {player.potential}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={rosterFull || signingId !== null}
              onClick={() => sign(player)}
              aria-label={`Sign ${player.full_name}`}
            >
              {signingId === player.id ? "Signing…" : "Sign"}
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-mist">
        One-year deals at market value. Minimum contract is {formatMoney(750_000)}.
      </p>
    </Dialog>
  );
}
