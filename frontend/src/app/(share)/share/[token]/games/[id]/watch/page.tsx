import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { WatchView } from "@/components/watch/WatchView";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Watch" };

export default function SharedWatchPage(props: PageProps<"/share/[token]/games/[id]/watch">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto aspect-video max-w-7xl" />}>
      <Content {...props} />
    </Suspense>
  );
}

async function Content({ params, searchParams }: PageProps<"/share/[token]/games/[id]/watch">) {
  const { token, id } = await params;
  const { play, auto, highlights } = await searchParams;
  const result = await attempt(() => api.publicPlayback(token, Number(id)));
  if (!result.ok) return <ServerError error={result.error} />;
  return <WatchView playback={result.data} initialPlay={Number(play) || undefined}
    initialAuto={auto === "1"} initialHighlights={highlights === "1"} site={sharedSite(token)} />;
}
