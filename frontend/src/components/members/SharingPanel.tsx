"use client";

import { useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";

const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

export function shareUrl(origin: string, token: string): string {
  return `${origin}/share/${encodeURIComponent(token)}`;
}

/**
 * Sharing and export: a commissioner makes (or stops) a read-only public link to the
 * league; any member downloads the whole league as JSON.
 */
export function SharingPanel({ leagueId, commissioner, initialSharedAt }: {
  leagueId: number; commissioner: boolean; initialSharedAt: string | null;
}) {
  const [sharedAt, setSharedAt] = useState(initialSharedAt);
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function share() {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const made = await api.shareLeague(leagueId);
      setLink(shareUrl(window.location.origin, made.token));
      setSharedAt(made.shared_at);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    setBusy(true);
    setError(null);
    try {
      await api.unshareLeague(leagueId);
      setLink(null);
      setSharedAt(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
    <Panel title="Share and export">
      <div className="space-y-4">
        {commissioner && (
          <div className="space-y-2">
            <p className="text-sm text-mist">
              {sharedAt
                ? `Shared since ${day.format(new Date(sharedAt))}: anyone with the link sees the standings, ` +
                  "schedule, box scores, stats and history (no contracts, nothing they can change)."
                : "Not shared. A read-only link lets anyone follow the league without an account."}
            </p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={share}>
                {sharedAt ? "New public link" : "Share a read-only link"}
              </button>
              {sharedAt && (
                <button type="button" className="btn btn-ghost" disabled={busy} onClick={stop}>Stop sharing</button>
              )}
            </div>
            {sharedAt && !link && (
              <p className="text-xs text-mist">The link is shown once. Make a new one to copy it again (the old one stops).</p>
            )}
            {link && (
              <div className="flex flex-wrap items-center gap-2">
                <label className="min-w-0 flex-1 space-y-1">
                  <span className="eyebrow">Public link (shown once)</span>
                  <input className="field-input w-full" readOnly value={link}
                    onFocus={(e) => e.currentTarget.select()} />
                </label>
                <button type="button" className="btn btn-ghost self-end" onClick={copy}>Copy</button>
                {copied && <span role="status" className="self-end text-sm text-emerald-300">Copied.</span>}
              </div>
            )}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3 border-t border-white/5 pt-4">
          <a href={`/api/leagues/${leagueId}/export`} download className="btn btn-ghost">
            Download the league (JSON)
          </a>
          <span className="text-xs text-mist">
            Teams, players, ratings, contracts, every season&apos;s results, awards and trades.
          </span>
        </div>
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      </div>
    </Panel>
  );
}
