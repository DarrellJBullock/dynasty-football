import type { Metadata } from "next";
import { Suspense } from "react";
import { BracketView } from "@/components/season/BracketView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Playoffs" };

export default function PlayoffsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading playoffs">
          <Skeleton className="h-16 w-96" />
          <div className="grid gap-6 md:grid-cols-2">
            <Skeleton className="h-72" />
            <Skeleton className="h-72" />
          </div>
        </div>
      }
    >
      <PlayoffsContent />
    </Suspense>
  );
}

async function PlayoffsContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, bracket: await api.playoffs(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <BracketView bracket={result.data.bracket} teamId={result.data.franchise.team.id} />;
}
