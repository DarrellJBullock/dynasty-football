import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { CoachLoader } from "@/components/coach/CoachLoader";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Play Game" };

/**
 * "Play Game": the franchise's next game in Coach Mode. Rendered here rather than by
 * redirecting to /games/[id]/coach: the client router remembers a redirect, so after the
 * game is played "Play Game" would keep opening it.
 */
export default function PlayGamePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-4" aria-busy="true" aria-label="Loading game">
          <Skeleton className="h-16" />
          <Skeleton className="aspect-video" />
        </div>
      }
    >
      <NextGame />
    </Suspense>
  );
}

async function NextGame() {
  const result = await attempt(() => api.nextGame());
  if (!result.ok) return <ServerError error={result.error} />;
  if (result.data.game) return <CoachLoader gameId={result.data.game.id} />;
  return (
    <div className="mx-auto max-w-3xl">
      <section className="panel space-y-3 p-6 text-center" aria-label="Play Game">
        <h1 className="font-display text-2xl font-bold uppercase">No game to play</h1>
        <p className="text-sm text-mist">
          Your team doesn&apos;t have a game left to play this week. Simulate the week (or
          move the season along) from the Dashboard or Schedule, then come back to coach the
          next one.
        </p>
        <div className="flex justify-center gap-3 text-sm">
          <Link href="/" className="text-gold hover:underline">Dashboard</Link>
          <Link href="/schedule" className="text-gold hover:underline">Schedule</Link>
        </div>
      </section>
    </div>
  );
}
