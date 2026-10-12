import type { Metadata } from "next";
import { Suspense } from "react";
import { RosterManager } from "@/components/roster/RosterManager";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Roster" };

export default function RosterPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading roster">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-16" />
          <Skeleton className="h-[600px]" />
        </div>
      }
    >
      <RosterContent />
    </Suspense>
  );
}

async function RosterContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const [team, roster] = await Promise.all([
      api.team(franchise.team.id),
      api.roster(franchise.team.id),
    ]);
    return { franchise, team, roster };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, team, roster } = result.data;
  return (
    <RosterManager
      initialTeam={team}
      initialRoster={roster}
      leagueId={franchise.league.id}
      seasonYear={franchise.season.year}
      capYear={franchise.season.year + (franchise.season.phase === "offseason" ? 1 : 0)}
    />
  );
}
