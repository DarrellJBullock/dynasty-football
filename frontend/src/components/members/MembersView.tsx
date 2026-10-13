"use client";

import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { LeagueSettingsPanel } from "./LeagueSettingsPanel";
import { SharingPanel } from "./SharingPanel";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { Invite, Member, Members } from "@/lib/types";

/** The link a friend opens to join (the token is only known when the invite is made). */
export function inviteUrl(origin: string, token: string): string {
  return `${origin}/join?token=${encodeURIComponent(token)}`;
}

const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

/**
 * A league's members: who runs which team, and the teams still open. A commissioner also
 * makes and revokes invite links, changes roles and removes members; anyone can leave.
 */
export function MembersView({ initial }: { initial: Members }) {
  const [view, setView] = useState(initial);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const leagueId = view.league.id;
  const commissioner = view.you.role === "commissioner";

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const refresh = async () => setView(await api.members(leagueId));

  const invite = () => run(async () => {
    const made = await api.createInvite(leagueId);
    setLink(inviteUrl(window.location.origin, made.token));
    setCopied(false);
    await refresh();
  });

  const revoke = (item: Invite) => run(async () => {
    await api.revokeInvite(leagueId, item.id);
    await refresh();
  });

  const setRole = (member: Member, role: Member["role"]) => run(async () => {
    setView(await api.setMemberRole(leagueId, member.id, role));
  });

  const remove = (member: Member) => run(async () => {
    await api.removeMember(leagueId, member.id);
    if (member.is_you) hardNavigate("/leagues"); // (the league isn't yours to see any more)
    else await refresh();
  });

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setError("Couldn't copy: select the link and copy it yourself.");
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow={view.league.name} title="Members">
        <p className="text-sm text-mist">
          {view.members.length} {view.members.length === 1 ? "member" : "members"} ·{" "}
          {view.open_teams.length} open {view.open_teams.length === 1 ? "team" : "teams"} (the AI runs them)
        </p>
      </PageHeader>

      {error && (
        <p role="alert" className="mb-4 rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
          {error}
        </p>
      )}

      <div className="space-y-6">
        <Panel title="Who's in">
          <ul className="divide-y divide-white/5">
            {view.members.map((member) => (
              <li key={member.id} aria-label={member.display_name}
                className="flex flex-wrap items-center gap-3 py-3">
                {member.team ? <TeamCrest team={member.team} size={32} /> : <span className="w-8" />}
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">
                    {member.display_name}
                    {member.is_you && <span className="ml-2 text-xs text-mist">(you)</span>}
                  </div>
                  <div className="text-sm text-mist">
                    {member.role === "commissioner" ? "Commissioner" : "Manager"}
                    {" · "}
                    {member.team ? member.team.full_name : "No team"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {commissioner && !member.is_you && (
                    <button type="button" className="btn btn-ghost" disabled={busy}
                      onClick={() => setRole(member, member.role === "commissioner" ? "manager" : "commissioner")}>
                      {member.role === "commissioner" ? "Make manager" : "Make commissioner"}
                    </button>
                  )}
                  {(member.is_you || commissioner) && (
                    <RemoveButton member={member} busy={busy} onConfirm={() => remove(member)} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        {commissioner && (
          <Panel title="Invite friends"
            action={<button type="button" className="btn btn-primary" disabled={busy} onClick={invite}>
              New invite link
            </button>}>
            <p className="text-sm text-mist">
              Anyone with a link can join and pick an open team, for a week. Revoke a link to stop it working.
            </p>
            {link && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <label className="min-w-0 flex-1 space-y-1">
                  <span className="eyebrow">Invite link (shown once)</span>
                  <input className="field-input w-full" readOnly value={link}
                    onFocus={(e) => e.currentTarget.select()} />
                </label>
                <button type="button" className="btn btn-ghost self-end" onClick={copy}>Copy</button>
                {copied && <span role="status" className="self-end text-sm text-emerald-300">Copied.</span>}
              </div>
            )}
            {view.invites.length > 0 && (
              <ul className="mt-4 divide-y divide-white/5" aria-label="Open invite links">
                {view.invites.map((item) => (
                  <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span>
                      Made {day.format(new Date(item.created_at))}, expires {day.format(new Date(item.expires_at))}
                      {" · "}used {item.uses} {item.uses === 1 ? "time" : "times"}
                    </span>
                    <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => revoke(item)}>
                      Revoke
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}

        {commissioner && <LeagueSettingsPanel leagueId={leagueId} />}

        <SharingPanel leagueId={leagueId} commissioner={commissioner} initialSharedAt={view.shared_at} />

        <Panel title="Open teams">
          {view.open_teams.length === 0 ? (
            <p className="text-sm text-mist">Every team has a manager.</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {view.open_teams.map((team) => (
                <li key={team.id} className="flex items-center gap-2 text-sm">
                  <TeamCrest team={team} size={22} />
                  {team.full_name}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function RemoveButton({ member, busy, onConfirm }: {
  member: Member; busy: boolean; onConfirm: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const label = member.is_you ? "Leave league" : "Remove";
  if (!confirming) {
    return (
      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirming(true)}>
        {label}…
      </button>
    );
  }
  return (
    <span className="flex items-center gap-2 text-sm">
      {member.team ? `${member.team.nickname} go back to the AI.` : ""}
      <button type="button" className="btn btn-danger" disabled={busy} onClick={onConfirm}>
        {member.is_you ? "Leave" : `Remove ${member.display_name}`}
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
    </span>
  );
}
