import type { Metadata } from "next";
import { Suspense } from "react";
import { GameView } from "@/components/season/GameView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";
import { sharedSite } from "@/lib/site";

export const metadata: Metadata = { title: "Game" };

export default function SharedGamePage({ params }: PageProps<"/share/[token]/games/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-6xl" />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: Pick<PageProps<"/share/[token]/games/[id]">, "params">) {
  const { token, id } = await params;
  const result = await attempt(() => api.publicGame(token, Number(id)));
  if (!result.ok) return <ServerError error={result.error} />;
  return <GameView detail={result.data} site={sharedSite(token)} />;
}
