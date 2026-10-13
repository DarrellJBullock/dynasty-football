"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export const POLL_MS = 30_000;

/**
 * The inbox's unread count, for the sidebar: polled every 30 seconds while the page is
 * visible, again on each page change and when you come back to the tab (no always-open
 * connections), and told directly when the inbox marks things read.
 */
export function UnreadBadge({ pathname }: { pathname: string | null }) {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let live = true;
    const check = () => {
      if (document.visibilityState !== "visible") return;
      api.unreadCount().then((r) => { if (live) setUnread(r.unread); }, () => {});
    };
    check();
    const timer = setInterval(check, POLL_MS);
    const told = (e: Event) => setUnread((e as CustomEvent<number>).detail);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("dynasty:unread", told);
    return () => {
      live = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("dynasty:unread", told);
    };
  }, [pathname]);

  if (!unread) return null;
  return (
    <span className="ml-auto rounded-full bg-gold px-1.5 text-[11px] font-semibold leading-5 text-ink-950">
      {unread > 99 ? "99+" : unread}
      <span className="sr-only"> unread</span>
    </span>
  );
}

/**
 * Coming back to the tab shows what changed while you were away (another manager's trade,
 * the week played): the page's server data is fetched again. Client state is kept.
 */
export function RefreshOnReturn() {
  const router = useRouter();
  useEffect(() => {
    let away = false;
    const changed = () => {
      if (document.visibilityState === "hidden") away = true;
      else if (away) {
        away = false;
        router.refresh();
      }
    };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, [router]);
  return null;
}
