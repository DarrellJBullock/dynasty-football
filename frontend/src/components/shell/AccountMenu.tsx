"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";

/** Who's signed in, with Account and Sign out (in the sidebar). */
export function AccountMenu() {
  const [email, setEmail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api.me().then((user) => live && setEmail(user.email), () => {});
    return () => {
      live = false;
    };
  }, []);

  async function signOut() {
    setBusy(true);
    try {
      await api.signOut();
    } finally {
      hardNavigate("/signin");
    }
  }

  return (
    <div role="group" aria-label="Account"
      className="flex items-center gap-2 border-t border-white/5 px-4 py-2 text-xs lg:mt-auto lg:flex-col lg:items-stretch lg:px-5 lg:py-4">
      <Link href="/account" className="min-w-0 truncate text-mist hover:text-chalk" title={email ?? undefined}>
        {email ?? "Account"}
      </Link>
      <button type="button" className="btn btn-ghost px-2 py-1 text-xs" disabled={busy} onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
