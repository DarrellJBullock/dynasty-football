import { ServerError } from "@/components/ui/ServerError";
import { ApiError, api, attempt } from "@/lib/api";
import { CoachView } from "./CoachView";

/** Loads a game for Coach Mode (the game, the playbook, and the coached state if any). */
export async function CoachLoader({ gameId }: { gameId: number }) {
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
