import type { Metadata } from "next";
import { Suspense } from "react";
import { ContractsView } from "@/components/contracts/ContractsView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Contracts" };

export default function ContractsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading contracts">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-28" />
          <Skeleton className="h-[500px]" />
        </div>
      }
    >
      <ContractsContent />
    </Suspense>
  );
}

async function ContractsContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, contracts: await api.contracts(franchise.team.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <ContractsView data={result.data.contracts} team={result.data.franchise.team} />;
}
