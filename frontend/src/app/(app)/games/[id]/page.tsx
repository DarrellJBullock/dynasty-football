import type { Metadata } from "next";
import { Suspense } from "react";
import { GameView } from "@/components/season/GameView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Game" };

export default function GamePage({ params }: PageProps<"/games/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading game">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-32" />
          <div className="grid gap-6 lg:grid-cols-2">
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
          </div>
        </div>
      }
    >
      <GameContent params={params} />
    </Suspense>
  );
}

async function GameContent({ params }: Pick<PageProps<"/games/[id]">, "params">) {
  const { id } = await params;
  const result = await attempt(() => api.game(Number(id)));
  if (!result.ok) return <ServerError error={result.error} />;
  return <GameView detail={result.data} />;
}
