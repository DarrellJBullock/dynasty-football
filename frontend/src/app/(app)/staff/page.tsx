import type { Metadata } from "next";
import { Suspense } from "react";
import { StaffView } from "@/components/staff/StaffView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Staff" };

export default function StaffPage({ searchParams }: PageProps<"/staff">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-7xl" />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: Pick<PageProps<"/staff">, "searchParams">) {
  const { team } = await searchParams;
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const teams = await api.leagueTeams(franchise.league.id);
    const teamId = teams.some((t) => t.id === Number(team)) ? Number(team) : franchise.team.id;
    // (in turn, not at once: a league from before staff gets its staff on the first read)
    const staff = await api.teamStaff(teamId);
    const coaches = await api.coaches(franchise.league.id);
    const market = teamId === franchise.team.id ? await api.staffMarket(franchise.league.id) : null;
    return { franchise, teams, staff, coaches, market };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, teams, staff, coaches, market } = result.data;
  return <StaffView key={staff.team.id} staff={staff} coaches={coaches} teams={teams}
    season={franchise.season.year} market={market} leagueId={franchise.league.id} />;
}
