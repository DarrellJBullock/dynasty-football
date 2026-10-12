import type { Metadata } from "next";
import { Suspense } from "react";
import { DynastyReportView } from "@/components/dynasty/DynastyReportView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Dynasty report" };

export default function DynastyPage({ searchParams }: PageProps<"/dynasty">) {
  return (
    <Suspense fallback={
      <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading the report">
        <Skeleton className="h-16 w-96" />
        <Skeleton className="h-64" />
      </div>
    }>
      <DynastyContent searchParams={searchParams} />
    </Suspense>
  );
}

async function DynastyContent({ searchParams }: Pick<PageProps<"/dynasty">, "searchParams">) {
  const params = await searchParams;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const latest = franchise.season.year - 1;
    const to = Number(params.to) || latest;
    const from = Number(params.from) || to - 9; // (seasons before the first are skipped)
    return { franchise, report: await api.dynastyReport(franchise.league.id, from, to) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, report } = result.data;
  return <DynastyReportView report={report} team={franchise.team} league={franchise.league.name} />;
}
