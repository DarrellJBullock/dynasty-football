import type { Metadata } from "next";
import { Suspense } from "react";
import { PlayerView } from "@/components/stats/PlayerView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Player" };

export default function PlayerPage({ params }: PageProps<"/players/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading player">
          <Skeleton className="h-32" />
          <Skeleton className="h-48" />
          <Skeleton className="h-64" />
        </div>
      }
    >
      <PlayerContent params={params} />
    </Suspense>
  );
}

async function PlayerContent({ params }: Pick<PageProps<"/players/[id]">, "params">) {
  const id = Number((await params).id);
  const result = await attempt(async () => {
    const [player, stats, career] = await Promise.all([
      api.player(id), api.playerStats(id), api.career(id),
    ]);
    return { player, stats, career };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { player, stats, career } = result.data;
  return <PlayerView player={player} stats={stats} career={career} />;
}
