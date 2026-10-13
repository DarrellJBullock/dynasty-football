"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/shell/Sidebar";
import { sharedSite } from "@/lib/site";

/** A public link's pages, and a note that it's read-only. */
export function ShareNav({ token }: { token: string }) {
  const pathname = usePathname();
  const { base } = sharedSite(token);
  const pages = [
    { label: "Standings", href: base },
    { label: "Schedule", href: `${base}/schedule` },
    { label: "Playoffs", href: `${base}/playoffs` },
    { label: "Stats", href: `${base}/stats` },
    { label: "History", href: `${base}/history` },
  ];
  const current = (href: string) =>
    href === base ? pathname === base : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <header className="sticky top-0 z-30 border-b border-white/5 bg-ink-900/90 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6 lg:px-10">
        <div className="flex items-center gap-2">
          <Logo />
          <span className="font-display text-lg font-bold uppercase tracking-wide">Dynasty</span>
        </div>
        <nav aria-label="League" className="flex gap-1 overflow-x-auto">
          {pages.map((p) => (
            <Link key={p.label} href={p.href} aria-current={current(p.href) ? "page" : undefined}
              className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${
                current(p.href) ? "bg-white/[0.07] font-medium text-chalk" : "text-mist hover:text-chalk"}`}>
              {p.label}
            </Link>
          ))}
        </nav>
        <span className="ml-auto text-xs text-mist">Read-only view of a shared league</span>
      </div>
    </header>
  );
}
