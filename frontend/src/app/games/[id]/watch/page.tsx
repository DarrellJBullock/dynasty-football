import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { WatchView } from "@/components/watch/WatchView";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Watch" };

export default function WatchPage({ params, searchParams }: PageProps<"/games/[id]/watch">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-4" aria-busy="true" aria-label="Loading game">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="aspect-video" />
        </div>
      }
    >
      <WatchContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function WatchContent({ params, searchParams }: PageProps<"/games/[id]/watch">) {
  const { id } = await params;
  const { play, auto, highlights } = await searchParams;
  const result = await attempt(() => api.playback(Number(id)));
  if (!result.ok) return <ServerError error={result.error} />;
  return <WatchView playback={result.data} initialPlay={Number(play) || undefined}
    initialAuto={auto === "1"} initialHighlights={highlights === "1"} />;
}
