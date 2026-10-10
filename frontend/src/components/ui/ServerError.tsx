import { ApiError } from "@/lib/api";

/** Shown in place of page content when the game API can't be reached or returns an error. */
export function ServerError({ error }: { error: unknown }) {
  const offline = error instanceof ApiError && error.status === 0;
  const notSeeded = error instanceof ApiError && error.status === 404;
  return (
    <div className="panel mx-auto mt-10 max-w-xl p-8 text-center">
      <div className="eyebrow text-rose-300">
        {offline ? "Game server offline" : notSeeded ? "No league yet" : "Something went wrong"}
      </div>
      <p className="mt-3 text-sm text-mist">
        {error instanceof Error ? error.message : "Unknown error"}
      </p>
      <div className="mt-6 rounded-lg bg-ink-950/80 p-4 text-left font-mono text-xs text-chalk/80">
        {offline ? (
          <>
            <div className="text-mist"># start the API (from the project root)</div>
            <div>make dev-backend</div>
          </>
        ) : (
          <>
            <div className="text-mist"># create the sample league</div>
            <div>make seed</div>
          </>
        )}
      </div>
    </div>
  );
}
