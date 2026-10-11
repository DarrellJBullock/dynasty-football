import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { LeaderCards, LeaderTable } from "@/components/stats/LeadersView";
import { TeamStatsTable } from "@/components/stats/TeamStatsTable";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { formatPhase } from "@/lib/format";

export const metadata: Metadata = { title: "Stats" };

export default function StatsPage({ searchParams }: PageProps<"/stats">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading stats">
          <Skeleton className="h-16 w-96" />
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-56" />)}
          </div>
        </div>
      }
    >
      <StatsContent searchParams={searchParams} />
    </Suspense>
  );
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

async function StatsContent({ searchParams }: Pick<PageProps<"/stats">, "searchParams">) {
  const params = await searchParams;
  const view = first(params.view) === "teams" ? "teams" : "leaders";
  const category = first(params.category);
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const leagueId = franchise.league.id;
    if (view === "teams") return { franchise, teams: await api.teamStats(leagueId) };
    return { franchise, leaders: await api.leaders(leagueId, category, category ? 25 : 5) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise } = result.data;
  const teamId = franchise.team.id;
  const tab = (href: string, label: string, active: boolean) => (
    <Link href={href} role="tab" aria-selected={active}
      className={`rounded-md px-3 py-1.5 font-display text-sm font-semibold uppercase tracking-wide ${
        active ? "bg-gold text-ink-950" : "text-mist hover:bg-white/5 hover:text-chalk"}`}>
      {label}
    </Link>
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{franchise.season.year} {formatPhase(franchise.season.phase)}</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Stats</h1>
        </div>
        <div role="tablist" aria-label="Stats view" className="flex gap-1">
          {tab("/stats", "Leaders", view === "leaders")}
          {tab("/stats?view=teams", "Teams", view === "teams")}
        </div>
      </div>
      {"teams" in result.data && result.data.teams ? (
        <TeamStatsTable rows={result.data.teams} teamId={teamId} />
      ) : category && result.data.leaders?.categories[0] ? (
        <>
          <Link href="/stats" className="text-sm text-gold hover:underline">← All leaders</Link>
          <LeaderTable category={result.data.leaders.categories[0]} teamId={teamId} />
        </>
      ) : (
        <LeaderCards categories={result.data.leaders?.categories ?? []} teamId={teamId} />
      )}
    </div>
  );
}
