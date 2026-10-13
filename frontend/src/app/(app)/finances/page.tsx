import type { Metadata } from "next";
import { Suspense } from "react";
import { FinancesView } from "@/components/finances/FinancesView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Finances" };

export default function FinancesPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading finances">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-36" />
          <Skeleton className="h-96" />
        </div>
      }
    >
      <FinancesContent />
    </Suspense>
  );
}

async function FinancesContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return api.finances(franchise.team.id);
  });
  if (!result.ok) return <ServerError error={result.error} />;
  // (key: a refresh with new numbers starts the view afresh)
  return <FinancesView key={JSON.stringify(result.data)} initial={result.data} canSetPrice />;
}
