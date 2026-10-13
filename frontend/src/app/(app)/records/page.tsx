import type { Metadata } from "next";
import { Suspense } from "react";
import { RecordsView } from "@/components/legacy/RecordsView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Records" };

export default function RecordsPage({ searchParams }: PageProps<"/records">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: Pick<PageProps<"/records">, "searchParams">) {
  const { team } = await searchParams;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const teams = await api.leagueTeams(franchise.league.id);
    const teamId = teams.some((t) => t.id === Number(team)) ? Number(team) : franchise.team.id;
    return { teams, book: await api.teamRecords(teamId) };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  return <RecordsView key={result.data.book.team.id} initial={result.data.book} teams={result.data.teams} />;
}
