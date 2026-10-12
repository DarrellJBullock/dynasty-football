"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { Brand } from "./AuthForm";

/** Ask for a password reset link by email. */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSent((await api.forgotPassword(email)).detail);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <Brand />
      <form onSubmit={submit} className="panel space-y-4 p-6" aria-label="Reset your password">
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide">Reset your password</h1>
        <p className="text-sm text-mist">We&apos;ll email you a link to choose a new one.</p>
        <label className="block space-y-1">
          <span className="eyebrow">Email</span>
          <input className="field-input" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {sent && <p role="status" className="text-sm text-emerald-300">{sent}</p>}
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Sending…" : "Email me a link"}
        </button>
        <p className="text-center text-sm">
          <Link className="text-gold hover:underline" href="/signin">Back to sign in</Link>
        </p>
      </form>
    </div>
  );
}

/** Choose a new password with the link's token (`?token=`). */
export function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== repeat) {
      setError("The passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <Brand />
      <form onSubmit={submit} className="panel space-y-4 p-6" aria-label="Choose a new password">
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide">Choose a new password</h1>
        {done ? (
          <>
            <p role="status" className="text-sm text-emerald-300">
              Your password is changed. You&apos;re signed out everywhere; sign in with the new one.
            </p>
            <Link className="btn btn-primary w-full justify-center" href="/signin">Sign in</Link>
          </>
        ) : (
          <>
            <label className="block space-y-1">
              <span className="eyebrow">New password</span>
              <input className="field-input" type="password" autoComplete="new-password" required
                minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="block space-y-1">
              <span className="eyebrow">New password again</span>
              <input className="field-input" type="password" autoComplete="new-password" required
                value={repeat} onChange={(e) => setRepeat(e.target.value)} />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy || !token}>
              {busy ? "Saving…" : "Set new password"}
            </button>
            {!token && (
              <p className="text-sm text-mist">
                This page needs the link from your email. <Link className="text-gold hover:underline"
                  href="/forgot-password">Ask for one</Link>.
              </p>
            )}
          </>
        )}
      </form>
    </div>
  );
}
