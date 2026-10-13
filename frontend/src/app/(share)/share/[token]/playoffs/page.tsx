import type { Metadata } from "next";
import { Suspense } from "react";
import { BracketView } from "@/components/season/BracketView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Playoffs" };

export default function SharedPlayoffsPage({ params }: PageProps<"/share/[token]/playoffs">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: Pick<PageProps<"/share/[token]/playoffs">, "params">) {
  const { token } = await params;
  const result = await attempt(() => api.publicPlayoffs(token));
  if (!result.ok) return <ServerError error={result.error} />;
  return <BracketView bracket={result.data} teamId={0} site={sharedSite(token)} />;
}
