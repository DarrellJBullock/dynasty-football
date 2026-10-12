import type { Metadata } from "next";
import { Suspense } from "react";
import { DraftView } from "@/components/draft/DraftView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Draft" };

export default function DraftPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading the draft">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-24" />
          <Skeleton className="h-[600px]" />
        </div>
      }
    >
      <DraftContent />
    </Suspense>
  );
}

async function DraftContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, draft: await api.draft(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, draft } = result.data;
  return <DraftView draft={draft} team={franchise.team} leagueId={franchise.league.id} />;
}
