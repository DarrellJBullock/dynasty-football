import type { Metadata } from "next";
import { Suspense } from "react";
import { CommissionerTools } from "@/components/league/CommissionerTools";
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
    const [player, stats, career, coaching, franchise] = await Promise.all([
      api.player(id), api.playerStats(id), api.career(id), api.playerCoaching(id), api.franchise(),
    ]);
    // The commissioner's edits (not for a retired player, or one in another league).
    const league = franchise.role === "commissioner" && player.retired_year === null
      ? await api.leagueTeams(franchise.league.id) : null;
    const teams = league && (player.team_id === null || league.some((t) => t.id === player.team_id))
      ? league : null;
    return { player, stats, career, coaching, teams };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { player, stats, career, coaching, teams } = result.data;
  return (
    <>
      <PlayerView player={player} stats={stats} career={career} coaching={coaching} />
      {teams && (
        <div className="mx-auto mt-6 max-w-6xl">
          <CommissionerTools key={player.id} player={player} teams={teams} />
        </div>
      )}
    </>
  );
}
