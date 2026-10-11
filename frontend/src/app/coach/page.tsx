import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Play Game" };

/** "Play Game": straight to the franchise's next game in Coach Mode. */
export default function PlayGamePage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-32 max-w-3xl" />}>
      <NextGame />
    </Suspense>
  );
}

async function NextGame() {
  const result = await attempt(() => api.nextGame());
  if (!result.ok) return <ServerError error={result.error} />;
  if (result.data.game) redirect(`/games/${result.data.game.id}/coach`);
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
