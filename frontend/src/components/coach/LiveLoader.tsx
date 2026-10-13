import { ServerError } from "@/components/ui/ServerError";
import { ApiError, api, attempt } from "@/lib/api";
import { LiveView } from "./LiveView";

/** Loads a head-to-head game (the game, the playbook, and the live game if one was offered). */
export async function LiveLoader({ gameId }: { gameId: number }) {
  const result = await attempt(async () => {
    const [detail, playbook] = await Promise.all([api.game(gameId), api.playbook()]);
    // Nobody has offered to play it live yet: the page offers to.
    const live = await api.liveGame(gameId).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    });
    const playing = live && live.status !== "proposed" && live.status !== "declined";
    const playback = playing ? await api.playback(gameId) : null;
    return { game: detail.game, playbook, live, playback };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { game, playbook, live, playback } = result.data;
  return <LiveView game={game} playbook={playbook} initialLive={live} initialPlayback={playback} />;
}
