import type { Metadata } from "next";
import { Suspense } from "react";
import { LiveLoader } from "@/components/coach/LiveLoader";
import { Skeleton } from "@/components/ui/Panel";

export const metadata: Metadata = { title: "Live Game" };

export default function LivePage({ params }: PageProps<"/games/[id]/live">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-4" aria-busy="true" aria-label="Loading game">
          <Skeleton className="h-16" />
          <Skeleton className="aspect-video" />
        </div>
      }
    >
      <LiveContent params={params} />
    </Suspense>
  );
}

async function LiveContent({ params }: Pick<PageProps<"/games/[id]/live">, "params">) {
  return <LiveLoader gameId={Number((await params).id)} />;
}
