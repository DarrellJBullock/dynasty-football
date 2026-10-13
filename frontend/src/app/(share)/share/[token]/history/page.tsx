import type { Metadata } from "next";
import { Suspense } from "react";
import { HistoryView } from "@/components/history/HistoryView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "History" };

export default function SharedHistoryPage({ params }: PageProps<"/share/[token]/history">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: Pick<PageProps<"/share/[token]/history">, "params">) {
  const { token } = await params;
  const result = await attempt(async () => ({
    home: await api.publicLeague(token), history: await api.publicHistory(token),
  }));
  if (!result.ok) return <ServerError error={result.error} />;
  return <HistoryView history={result.data.history} league={result.data.home.league.name}
    site={sharedSite(token)} />;
}
