"use client";

import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { User } from "@/lib/types";

/** The account page: change the password, or delete the account and its leagues. */
export function AccountView({ user }: { user: User }) {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Account" title="Your account">
        <p className="text-sm text-mist">Signed in as <span className="text-chalk">{user.email}</span></p>
      </PageHeader>
      <div className="space-y-6">
        <ChangePassword />
        <DeleteAccount />
      </div>
    </div>
  );
}

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setDone(false);
    if (next !== repeat) {
      setError("The new passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setRepeat("");
      setDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Change password">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3" aria-label="Change password">
        <PasswordField label="Current password" value={current} onChange={setCurrent}
          autoComplete="current-password" />
        <PasswordField label="New password" value={next} onChange={setNext} autoComplete="new-password" />
        <PasswordField label="New password again" value={repeat} onChange={setRepeat}
          autoComplete="new-password" />
        <div className="flex flex-wrap items-center gap-3 sm:col-span-3">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
          <span className="text-xs text-mist">Other browsers you&apos;re signed in on are signed out.</span>
          {done && <span role="status" className="text-sm text-emerald-300">Password changed.</span>}
          {error && <span role="alert" className="text-sm text-rose-300">{error}</span>}
        </div>
      </form>
    </Panel>
  );
}

function DeleteAccount() {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password);
      hardNavigate("/signup");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Panel title="Delete account">
      <p className="text-sm text-mist">
        Deletes your account and every league in it, with all their seasons. This can&apos;t be undone.
      </p>
      <button type="button" className="btn btn-danger mt-4" onClick={() => setOpen(true)}>
        Delete account…
      </button>
      {open && (
        <Dialog title="Delete your account?" onClose={() => setOpen(false)}>
          <form onSubmit={confirm} className="space-y-4" aria-label="Confirm account deletion">
            <p className="text-sm text-mist">Enter your password to delete your account and all your leagues.</p>
            <PasswordField label="Password" value={password} onChange={setPassword}
              autoComplete="current-password" />
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
              <button type="submit" className="btn btn-danger" disabled={busy || !password}>
                {busy ? "Deleting…" : "Delete everything"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </Panel>
  );
}

function PasswordField({ label, value, onChange, autoComplete }: {
  label: string; value: string; onChange: (value: string) => void; autoComplete: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="eyebrow">{label}</span>
      <input className="field-input" type="password" required autoComplete={autoComplete}
        value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
