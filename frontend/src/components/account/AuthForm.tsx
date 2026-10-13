"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Logo } from "@/components/shell/Sidebar";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";

/** Where to go after signing in: back where the visitor was headed, if it's one of ours. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

/** Sign in, or create an account. Either signs in and loads the app afresh. */
export function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signingUp = mode === "signup";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (signingUp) {
        const user = await api.signUp({ email, password });
        // A new account builds its first league (unless it took over existing ones, or
        // came from an invite link, which it goes back to).
        hardNavigate(next.startsWith("/join") || user.has_league ? next : "/leagues/new");
      } else {
        await api.signIn({ email, password });
        hardNavigate(next);
      }
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <Brand />
      <form onSubmit={submit} className="panel space-y-4 p-6"
        aria-label={signingUp ? "Create an account" : "Sign in"}>
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide">
          {signingUp ? "Create an account" : "Sign in"}
        </h1>
        <label className="block space-y-1">
          <span className="eyebrow">Email</span>
          <input className="field-input" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <div className="space-y-1">
          <label className="block space-y-1">
            <span className="eyebrow">Password</span>
            <input className="field-input" type="password" required minLength={signingUp ? 8 : undefined}
              autoComplete={signingUp ? "new-password" : "current-password"}
              aria-describedby={signingUp ? "password-hint" : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {signingUp && <p id="password-hint" className="text-xs text-mist">At least 8 characters.</p>}
        </div>
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy}>
          {busy ? (signingUp ? "Creating…" : "Signing in…") : signingUp ? "Create account" : "Sign in"}
        </button>
        {!signingUp && (
          <p className="text-center text-sm">
            <Link className="text-mist hover:text-chalk" href="/forgot-password">Forgot your password?</Link>
          </p>
        )}
        <p className="text-center text-sm text-mist">
          {signingUp ? "Already have an account? " : "New here? "}
          <Link className="text-gold hover:underline"
            href={`${signingUp ? "/signin" : "/signup"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`}>
            {signingUp ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </form>
    </div>
  );
}

/** The logo and name above the sign-in forms. */
export function Brand() {
  return (
    <div className="mb-6 flex items-center justify-center gap-3">
      <Logo />
      <div className="leading-none">
        <div className="font-display text-lg font-bold uppercase tracking-wide">Dynasty</div>
        <div className="eyebrow mt-0.5 text-[10px] text-gold">Football · Next Gen</div>
      </div>
    </div>
  );
}
