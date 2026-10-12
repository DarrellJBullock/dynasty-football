import type { Metadata } from "next";
import { Suspense } from "react";
import { HistoryView } from "@/components/history/HistoryView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "History" };

export default function HistoryPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading history">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-64" />
          <Skeleton className="h-96" />
        </div>
      }
    >
      <HistoryContent />
    </Suspense>
  );
}

async function HistoryContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, history: await api.history(franchise.league.id) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, history } = result.data;
  return <HistoryView history={history} team={franchise.team} league={franchise.league.name} />;
}
