import type { Metadata } from "next";
import { Suspense } from "react";
import { CoachLoader } from "@/components/coach/CoachLoader";
import { Skeleton } from "@/components/ui/Panel";

export const metadata: Metadata = { title: "Coach" };

export default function CoachPage({ params }: PageProps<"/games/[id]/coach">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-4" aria-busy="true" aria-label="Loading game">
          <Skeleton className="h-16" />
          <Skeleton className="aspect-video" />
        </div>
      }
    >
      <CoachContent params={params} />
    </Suspense>
  );
}

async function CoachContent({ params }: Pick<PageProps<"/games/[id]/coach">, "params">) {
  return <CoachLoader gameId={Number((await params).id)} />;
}
