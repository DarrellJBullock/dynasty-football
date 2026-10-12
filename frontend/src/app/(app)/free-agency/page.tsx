import type { Metadata } from "next";
import { Suspense } from "react";
import { FreeAgencyView } from "@/components/free-agency/FreeAgencyView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Free Agency" };

export default function FreeAgencyPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading free agency">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-24" />
          <Skeleton className="h-[600px]" />
        </div>
      }
    >
      <FreeAgencyContent />
    </Suspense>
  );
}

async function FreeAgencyContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, market: await api.freeAgency(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <FreeAgencyView market={result.data.market} team={result.data.franchise.team} />;
}
