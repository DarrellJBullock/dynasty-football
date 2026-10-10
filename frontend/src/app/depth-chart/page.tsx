import type { Metadata } from "next";
import { Suspense } from "react";
import { DepthChartEditor } from "@/components/depth-chart/DepthChartEditor";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Depth Chart" };

export default function DepthChartPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading depth chart">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-16" />
          <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
            <Skeleton className="h-[480px]" />
            <Skeleton className="h-[480px]" />
          </div>
        </div>
      }
    >
      <DepthChartContent />
    </Suspense>
  );
}

async function DepthChartContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return api.depthChart(franchise.team.id);
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <DepthChartEditor initialChart={result.data} />;
}
