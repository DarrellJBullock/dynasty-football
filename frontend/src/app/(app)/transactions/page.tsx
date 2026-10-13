import type { Metadata } from "next";
import { Suspense } from "react";
import { TransactionsView } from "@/components/transactions/TransactionsView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Transactions" };

export default function TransactionsPage({ searchParams }: PageProps<"/transactions">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-5xl space-y-6" aria-busy="true" aria-label="Loading transactions">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-96" />
        </div>
      }
    >
      <TransactionsContent searchParams={searchParams} />
    </Suspense>
  );
}

async function TransactionsContent({ searchParams }: Pick<PageProps<"/transactions">, "searchParams">) {
  const asked = Number((await searchParams).year) || undefined;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const history = await api.history(franchise.league.id);
    const years = history.seasons.map((s) => s.year);
    const current = franchise.season.year;
    const year = asked && asked <= current ? asked : current;
    return { current, first: Math.min(current, ...years), year,
      trades: await api.transactions(franchise.league.id, year) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { current, first, year, trades } = result.data;
  return <TransactionsView year={year} firstYear={first} currentYear={current} trades={trades} />;
}
