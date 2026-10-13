import type { Metadata } from "next";
import { Suspense } from "react";
import { HallOfFameView } from "@/components/legacy/HallOfFameView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Hall of Fame" };

export default function HallOfFamePage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-6xl" />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, hall: await api.hallOfFame(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <HallOfFameView hall={result.data.hall} league={result.data.franchise.league.name} />;
}
