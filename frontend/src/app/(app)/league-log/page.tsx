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
    const commissioner = franchise.role === "commissioner";
    const [log, rollback] = await Promise.all([
      api.leagueLog(franchise.league.id),
      commissioner ? api.rollback(franchise.league.id) : null,
    ]);
    return { leagueId: franchise.league.id, log, rollback };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { leagueId, log, rollback } = result.data;
  return <LeagueLogView leagueId={leagueId} initial={log}
    rollback={rollback ? rollback.label : undefined} />;
}
