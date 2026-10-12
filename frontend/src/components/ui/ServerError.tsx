import Link from "next/link";
import { ApiError } from "@/lib/api";

/** The game server's answer to a new account with no league (backend api/franchise.py). */
const NO_LEAGUE = "You don't have a league yet";

/** Shown in place of page content when the game API can't be reached or returns an error. */
export function ServerError({ error }: { error: unknown }) {
  const offline = error instanceof ApiError && error.status === 0;
  const noLeague = error instanceof ApiError && error.status === 404 && error.message.startsWith(NO_LEAGUE);
  return (
    <div className="panel mx-auto mt-10 max-w-xl p-8 text-center">
      <div className="eyebrow text-rose-300">
        {offline ? "Game server offline" : noLeague ? "No league yet" : "Something went wrong"}
      </div>
      <p className="mt-3 text-sm text-mist">
        {error instanceof Error ? error.message : "Unknown error"}
      </p>
      {noLeague && (
        <Link href="/leagues/new" className="btn btn-primary mt-6 inline-flex">Build your league</Link>
      )}
      {offline && (
        <div className="mt-6 rounded-lg bg-ink-950/80 p-4 text-left font-mono text-xs text-chalk/80">
          <div className="text-mist"># start the API (from the project root)</div>
          <div>make dev-backend</div>
        </div>
      )}
    </div>
  );
}
