import type { Metadata } from "next";
import { Suspense } from "react";
import { ScheduleView } from "@/components/season/ScheduleView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Schedule" };

export default function SharedSchedulePage(props: PageProps<"/share/[token]/schedule">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-6xl" />}>
      <Content {...props} />
    </Suspense>
  );
}

async function Content({ params, searchParams }: PageProps<"/share/[token]/schedule">) {
  const { token } = await params;
  const { week } = await searchParams;
  const result = await attempt(() => api.publicSchedule(token, Number(week) || undefined));
  if (!result.ok) return <ServerError error={result.error} />;
  return <ScheduleView schedule={result.data} teamId={0} site={sharedSite(token)} />;
}
