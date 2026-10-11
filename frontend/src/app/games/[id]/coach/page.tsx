import type { Metadata } from "next";
import { Suspense } from "react";
import { CoachView } from "@/components/coach/CoachView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { ApiError, api, attempt } from "@/lib/api";

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
  const gameId = Number((await params).id);
  const result = await attempt(async () => {
    const [detail, playbook] = await Promise.all([api.game(gameId), api.playbook()]);
    // Not coaching it yet: the page offers to start.
    const state = await api.coachState(gameId).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    });
    const playback = state ? await api.playback(gameId) : null;
    return { game: detail.game, playbook, state, playback };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { game, playbook, state, playback } = result.data;
  return <CoachView game={game} playbook={playbook} initialState={state} initialPlayback={playback} />;
}
