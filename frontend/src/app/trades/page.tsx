import type { Metadata } from "next";
import { Suspense } from "react";
import { TradesView } from "@/components/trades/TradesView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Trades" };

export default function TradesPage({ searchParams }: PageProps<"/trades">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading trades">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-[600px]" />
        </div>
      }
    >
      <TradesContent searchParams={searchParams} />
    </Suspense>
  );
}

async function TradesContent({ searchParams }: Pick<PageProps<"/trades">, "searchParams">) {
  const { partner } = await searchParams;
  const partnerId = typeof partner === "string" ? Number(partner) || undefined : undefined;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, center: await api.tradeCenter(franchise.league.id, partnerId) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, center } = result.data;
  return (
    <TradesView key={center.partner?.id} center={center} team={franchise.team}
      leagueId={franchise.league.id} />
  );
}
