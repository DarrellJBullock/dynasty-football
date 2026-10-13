import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatPhase } from "@/lib/format";
import type { Transaction } from "@/lib/types";

const BETWEEN: Record<Transaction["between"], string> = {
  ai: "Between AI teams", managers: "Between managers", manager_and_ai: "A manager and the AI",
};

function items(list: Transaction["sent"]): string {
  return list.map((i) => i.label).join(", ") || "nothing";
}

/** Every trade in a season, newest first: between managers, with the AI, and between AI teams. */
export function TransactionsView({ year, firstYear, currentYear, trades }: {
  year: number; firstYear: number; currentYear: number; trades: Transaction[];
}) {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader eyebrow="The league" title="Transactions">
        <nav aria-label="Seasons" className="flex items-center gap-2 text-sm">
          {year > firstYear && (
            <Link href={`/transactions?year=${year - 1}`} className="text-gold hover:underline">← {year - 1}</Link>
          )}
          <span className="font-semibold">{year}</span>
          {year < currentYear && (
            <Link href={`/transactions?year=${year + 1}`} className="text-gold hover:underline">{year + 1} →</Link>
          )}
        </nav>
      </PageHeader>
      <Panel title={`${year} trades`}>
        {trades.length === 0 ? (
          <p className="text-sm text-mist">No trades in {year}.</p>
        ) : (
          <ul className="divide-y divide-white/[0.05]" aria-label="Trades">
            {trades.map((t) => (
              <li key={t.id} className="space-y-1 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <TeamCrest team={t.team} size={20} />
                  <span className="font-semibold">{t.team.full_name}</span>
                  <span className="text-mist">and</span>
                  <TeamCrest team={t.partner} size={20} />
                  <span className="font-semibold">{t.partner.full_name}</span>
                  <span className="ml-auto flex items-center gap-2 text-xs text-mist">
                    {t.reversed && <span className="rounded bg-white/[0.06] px-1.5 py-0.5">Reversed</span>}
                    <span className="rounded bg-white/[0.06] px-1.5 py-0.5">{BETWEEN[t.between]}</span>
                    {t.season_phase === "regular_season" ? `Week ${t.week}` : formatPhase(t.season_phase)}
                  </span>
                </div>
                <p>
                  <span className="text-mist">The {t.team.nickname} sent</span> {items(t.sent)}{" "}
                  <span className="text-mist">for</span> {items(t.received)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
