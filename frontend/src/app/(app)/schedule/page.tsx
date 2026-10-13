import type { Metadata } from "next";
import { Suspense } from "react";
import { ScheduleView } from "@/components/season/ScheduleView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Schedule" };

export default function SchedulePage({ searchParams }: PageProps<"/schedule">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading schedule">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-12" />
          <div className="grid gap-3 md:grid-cols-2">
            {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-20" />)}
          </div>
        </div>
      }
    >
      <ScheduleContent searchParams={searchParams} />
    </Suspense>
  );
}

async function ScheduleContent({ searchParams }: Pick<PageProps<"/schedule">, "searchParams">) {
  const raw = (await searchParams).week;
  const week = Number(Array.isArray(raw) ? raw[0] : raw) || undefined;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, schedule: await api.schedule(franchise.league.id, week) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <ScheduleView schedule={result.data.schedule} teamId={result.data.franchise.team.id}
    canRun={result.data.franchise.role === "commissioner"} />;
}
