"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { InvitePreview } from "@/lib/types";

/** An invite link (`/join?token=…`): see the league, pick an open team, and join. */
export function JoinLeague() {
  const token = useSearchParams().get("token") ?? "";
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [teamId, setTeamId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let live = true;
    api.previewInvite(token).then(
      (found) => { if (live) setPreview(found); },
      (e: Error) => { if (live) setError(e.message); },
    );
    return () => { live = false; };
  }, [token]);

  async function join(event: React.FormEvent) {
    event.preventDefault();
    if (teamId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.joinLeague(token, teamId);
      hardNavigate("/"); // (the new franchise is active: load everything afresh)
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="panel w-full max-w-lg space-y-4 p-6">
      <div className="eyebrow text-gold">Invitation</div>
      <h1 className="font-display text-3xl font-bold uppercase tracking-wide">
        {preview ? `Join ${preview.league.name}` : "Join a league"}
      </h1>
      {!token && <p role="alert" className="text-sm text-rose-300">This link is missing its code. Ask for a new one.</p>}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      {token && !preview && !error && <p className="text-sm text-mist">Loading the invitation…</p>}
      {preview && preview.your_team && (
        <p className="text-sm text-mist">
          You already run the {preview.your_team.full_name} here.{" "}
          <Link className="text-gold hover:underline" href="/leagues">Go to My Leagues</Link>
        </p>
      )}
      {preview && !preview.your_team && (
        <form onSubmit={join} className="space-y-4" aria-label="Join the league">
          <p className="text-sm text-mist">
            {preview.commissioner} is the commissioner · {preview.member_count}{" "}
            {preview.member_count === 1 ? "member" : "members"}. Pick a team to run; the AI runs the rest.
          </p>
          {preview.open_teams.length === 0 ? (
            <p className="text-sm text-mist">Every team is taken.</p>
          ) : (
            <fieldset className="max-h-80 space-y-1 overflow-y-auto">
              <legend className="eyebrow mb-2">Open teams</legend>
              {preview.open_teams.map((team) => (
                <label key={team.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white/5">
                  <input type="radio" name="team" value={team.id} checked={teamId === team.id}
                    onChange={() => setTeamId(team.id)} />
                  <TeamCrest team={team} size={24} />
                  <span>{team.full_name}</span>
                  <span className="ml-auto text-xs text-mist">{team.division}</span>
                </label>
              ))}
            </fieldset>
          )}
          <button type="submit" className="btn btn-primary w-full justify-center"
            disabled={busy || teamId === null}>
            {busy ? "Joining…" : "Join the league"}
          </button>
        </form>
      )}
    </div>
  );
}
