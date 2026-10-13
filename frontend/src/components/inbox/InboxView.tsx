"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import type { Notification, NotificationSettings, Notifications } from "@/lib/types";

const when = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Tells the sidebar's badge the count changed (it listens; see UnreadBadge). */
export function announceUnread(unread: number) {
  window.dispatchEvent(new CustomEvent("dynasty:unread", { detail: unread }));
}

/**
 * The inbox: your notifications, newest first (opening one marks it read), and which
 * kinds from this league also come by email.
 */
export function InboxView({ initial, settings, leagueId, leagueName }: {
  initial: Notifications; settings: NotificationSettings | null; leagueId: number | null;
  leagueName: string | null;
}) {
  const [inbox, setInbox] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  async function markRead(ids?: number[]) {
    setError(null);
    try {
      const { unread } = await api.markRead(ids);
      setInbox((current) => ({
        unread,
        items: current.items.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)),
      }));
      announceUnread(unread);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Notifications" title="Inbox">
        {inbox.unread > 0 && (
          <button type="button" className="btn btn-ghost" onClick={() => markRead()}>
            Mark all read
          </button>
        )}
      </PageHeader>
      {error && <p role="alert" className="mb-4 text-sm text-rose-300">{error}</p>}
      <div className="space-y-6">
        <Panel title={inbox.unread ? `${inbox.unread} unread` : "All caught up"}>
          {inbox.items.length === 0 ? (
            <p className="text-sm text-mist">
              Nothing yet. Your picks, trade offers and results will show up here.
            </p>
          ) : (
            <ul className="divide-y divide-white/5" aria-label="Notifications">
              {inbox.items.map((n) => <Item key={n.id} note={n} onOpen={() => !n.read && markRead([n.id])} />)}
            </ul>
          )}
        </Panel>
        {settings && leagueId !== null && (
          <EmailSettings initial={settings} leagueId={leagueId} leagueName={leagueName} />
        )}
      </div>
    </div>
  );
}

function Item({ note, onOpen }: { note: Notification; onOpen: () => void }) {
  const content = (
    <>
      <div className="flex items-baseline gap-2">
        {!note.read && <span className="h-2 w-2 shrink-0 rounded-full bg-gold" aria-hidden />}
        <span className={note.read ? "text-mist" : "font-semibold"}>{note.title}</span>
        <span className="ml-auto shrink-0 text-xs text-mist">{when.format(new Date(note.created_at))}</span>
      </div>
      {note.body && <p className="mt-0.5 text-sm text-mist">{note.body}</p>}
      {note.league && <p className="mt-0.5 text-xs text-mist/70">{note.league}</p>}
    </>
  );
  return (
    <li aria-label={`${note.read ? "" : "Unread: "}${note.title}`}>
      {note.link ? (
        <Link href={note.link} onClick={onOpen} className="block rounded-lg px-2 py-3 hover:bg-white/[0.03]">
          {content}
        </Link>
      ) : (
        <button type="button" onClick={onOpen} className="block w-full rounded-lg px-2 py-3 text-left hover:bg-white/[0.03]">
          {content}
        </button>
      )}
    </li>
  );
}

function EmailSettings({ initial, leagueId, leagueName }: {
  initial: NotificationSettings; leagueId: number; leagueName: string | null;
}) {
  const [settings, setSettings] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(kind: string) {
    const chosen = settings.kinds.filter((k) => (k.kind === kind ? !k.email : k.email)).map((k) => k.kind);
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      setSettings(await api.setNotificationEmail(leagueId, chosen));
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title={`Email me${leagueName ? ` · ${leagueName}` : ""}`}>
      <p className="mb-3 text-sm text-mist">Everything shows up here. Pick what you also want by email.</p>
      <fieldset className="space-y-2">
        <legend className="sr-only">Email me about</legend>
        {settings.kinds.map((k) => (
          <label key={k.kind} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={k.email} disabled={busy} onChange={() => toggle(k.kind)} />
            {k.label}
          </label>
        ))}
      </fieldset>
      {saved && <p role="status" className="mt-3 text-sm text-emerald-300">Saved.</p>}
      {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
    </Panel>
  );
}
