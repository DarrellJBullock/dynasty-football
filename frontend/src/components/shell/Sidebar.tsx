"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  label: string;
  href?: string; // no href = planned feature
  icon: React.ReactNode;
}

const NAV: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Franchise",
    items: [
      { label: "Dashboard", href: "/", icon: <IconGrid /> },
      { label: "Roster", href: "/roster", icon: <IconUsers /> },
      { label: "Depth Chart", href: "/depth-chart", icon: <IconList /> },
      { label: "League", href: "/league", icon: <IconTrophy /> },
    ],
  },
  {
    heading: "Coming soon",
    items: [
      { label: "Schedule", icon: <IconCalendar /> },
      { label: "Draft & Trades", icon: <IconSwap /> },
      { label: "Play Game", icon: <IconPlay /> },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 z-30 border-b border-white/5 bg-ink-900/90 backdrop-blur lg:h-screen lg:w-60 lg:shrink-0 lg:border-b-0 lg:border-r">
      <div className="flex items-center gap-3 px-4 py-3 lg:px-5 lg:py-6">
        <Logo />
        <div className="leading-none">
          <div className="font-display text-lg font-bold uppercase tracking-wide">Dynasty</div>
          <div className="eyebrow mt-0.5 text-[10px] text-gold">Football · Next Gen</div>
        </div>
      </div>

      <nav aria-label="Main" className="overflow-x-auto px-2 pb-2 lg:px-3">
        {NAV.map((section) => (
          <div key={section.heading} className="contents lg:mb-6 lg:block">
            <div className="eyebrow hidden px-3 pb-2 lg:block">{section.heading}</div>
            <ul className="flex gap-1 lg:flex-col">
              {section.items.map((item) => {
                const active = item.href === pathname;
                if (!item.href) {
                  return (
                    <li key={item.label} className="hidden lg:block">
                      <span className="flex cursor-default items-center gap-3 rounded-lg px-3 py-2 text-sm text-mist/50">
                        {item.icon}
                        {item.label}
                      </span>
                    </li>
                  );
                }
                return (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-3 whitespace-nowrap rounded-lg px-3 py-2 text-sm transition-colors ${
                        active
                          ? "bg-white/[0.07] font-medium text-chalk shadow-[inset_2px_0_0_0_var(--color-gold)]"
                          : "text-mist hover:bg-white/[0.04] hover:text-chalk"
                      }`}
                    >
                      {item.icon}
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}

function Logo() {
  return (
    <svg viewBox="0 0 40 40" className="h-9 w-9" aria-hidden>
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f7cd6f" />
          <stop offset="1" stopColor="#c98a1b" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="36" height="36" rx="10" fill="#121924" stroke="url(#logo-g)" />
      <ellipse cx="20" cy="20" rx="12" ry="7.5" transform="rotate(-35 20 20)" fill="url(#logo-g)" />
      <path d="M15 24.5 25 15.5M17 19.5l2 2M19.5 17.5l2 2M14.5 21.5l2 2M22 15.5l2 2" stroke="#121924" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

const iconProps = {
  viewBox: "0 0 24 24",
  className: "h-4 w-4 shrink-0",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function IconGrid() {
  return (
    <svg {...iconProps}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  );
}
function IconUsers() {
  return (
    <svg {...iconProps}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5" />
      <path d="M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.8c1.6.8 2.6 2.6 3 5.2" />
    </svg>
  );
}
function IconTrophy() {
  return (
    <svg {...iconProps}>
      <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4Z" />
      <path d="M7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3" />
    </svg>
  );
}
function IconList() {
  return (
    <svg {...iconProps}>
      <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />
    </svg>
  );
}
function IconCalendar() {
  return (
    <svg {...iconProps}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  );
}
function IconSwap() {
  return (
    <svg {...iconProps}>
      <path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7" />
    </svg>
  );
}
function IconPlay() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <path d="m10 8.5 5 3.5-5 3.5v-7Z" />
    </svg>
  );
}
