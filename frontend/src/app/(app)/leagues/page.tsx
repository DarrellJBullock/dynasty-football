import type { Metadata } from "next";
import { Suspense } from "react";
import { LeaguesHub } from "@/components/leagues/LeaguesHub";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "My Leagues" };

export default function LeaguesPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading leagues">
          <Skeleton className="h-16 w-96" />
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
      }
    >
      <LeaguesContent />
    </Suspense>
  );
}

async function LeaguesContent() {
  const result = await attempt(api.franchises);
  if (!result.ok) return <ServerError error={result.error} />;
  return <LeaguesHub initialFranchises={result.data} />;
}
