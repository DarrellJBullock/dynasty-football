import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { LeaderCards, LeaderTable } from "@/components/stats/LeadersView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Stats" };

export default function SharedStatsPage(props: PageProps<"/share/[token]/stats">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content {...props} />
    </Suspense>
  );
}

async function Content({ params, searchParams }: PageProps<"/share/[token]/stats">) {
  const { token } = await params;
  const raw = (await searchParams).category;
  const category = typeof raw === "string" ? raw : undefined;
  const site = sharedSite(token);
  const result = await attempt(() => api.publicLeaders(token, category, category ? 25 : 5));
  if (!result.ok) return <ServerError error={result.error} />;
  const one = category ? result.data.categories[0] : undefined;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Stats</h1>
      {one ? (
        <>
          <Link href={`${site.base}/stats`} className="text-sm text-gold hover:underline">← All leaders</Link>
          <LeaderTable category={one} teamId={0} site={site} />
        </>
      ) : (
        <LeaderCards categories={result.data.categories} teamId={0} site={site} />
      )}
    </div>
  );
}
