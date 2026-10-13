import type { Metadata } from "next";
import { Suspense } from "react";
import { LeagueLogView } from "@/components/league/LeagueLogView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "League Log" };

export default function LeagueLogPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-4xl space-y-6" aria-busy="true" aria-label="Loading the League log">
          <Skeleton className="h-16" />
          <Skeleton className="h-96" />
        </div>
      }
    >
      <LeagueLogContent />
    </Suspense>
  );
}

async function LeagueLogContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { leagueId: franchise.league.id, log: await api.leagueLog(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <LeagueLogView leagueId={result.data.leagueId} initial={result.data.log} />;
}
