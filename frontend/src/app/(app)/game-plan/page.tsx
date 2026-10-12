import type { Metadata } from "next";
import { Suspense } from "react";
import { GamePlanEditor } from "@/components/gameplan/GamePlanEditor";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Game Plan" };

export default function GamePlanPage() {
  return (
    <Suspense fallback={
      <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading the game plan">
        <Skeleton className="h-16 w-96" />
        <Skeleton className="h-96" />
      </div>
    }>
      <GamePlanContent />
    </Suspense>
  );
}

async function GamePlanContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const [plan, playbook] = await Promise.all([api.gamePlan(franchise.team.id), api.playbook()]);
    return { franchise, plan, playbook };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, plan, playbook } = result.data;
  return <GamePlanEditor initial={plan} playbook={playbook} team={franchise.team} />;
}
