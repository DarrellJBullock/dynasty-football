import type { Metadata } from "next";
import { Suspense } from "react";
import { PublicStandings } from "@/components/share/PublicStandings";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Shared league" };

export default function SharedLeaguePage({ params }: PageProps<"/share/[token]">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: Pick<PageProps<"/share/[token]">, "params">) {
  const { token } = await params;
  const result = await attempt(async () => ({
    home: await api.publicLeague(token), standings: await api.publicStandings(token),
  }));
  if (!result.ok) return <ServerError error={result.error} />;
  return <PublicStandings home={result.data.home} standings={result.data.standings} site={sharedSite(token)} />;
}
