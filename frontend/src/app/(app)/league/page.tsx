import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { FrontOffices } from "@/components/league/FrontOffices";
import { LeagueRulesPanel } from "@/components/league/LeagueRulesPanel";
import { TeamEditButton } from "@/components/leagues/TeamEditButton";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { PageHeader, Panel, Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api, attempt } from "@/lib/api";
import { formatMoney, formatRecord } from "@/lib/format";

export const metadata: Metadata = { title: "League" };

export default function LeaguePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl space-y-6" aria-busy="true" aria-label="Loading league">
          <Skeleton className="h-16 w-96" />
          <div className="grid gap-6 md:grid-cols-2">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-56" />
            ))}
          </div>
        </div>
      }
    >
      <LeagueContent />
    </Suspense>
  );
}

async function LeagueContent() {
  const result = await attempt(async () => {
    const franchise = await api.franchise();
    const [standings, teams, rules, offices] = await Promise.all([
      api.standings(franchise.league.id),
      api.leagueTeams(franchise.league.id),
      api.leagueRules(franchise.league.id),
      api.frontOffices(franchise.league.id),
    ]);
    return { franchise, standings, teams, rules, offices };
  });
  if (!result.ok) return <ServerError error={result.error} />;
  const { franchise, standings, teams, rules, offices } = result.data;
  const ratings = new Map(teams.map((t) => [t.id, t]));
  const powerRanking = [...teams].sort((a, b) => b.ratings.overall - a.ratings.overall);
  const conferences = [...new Set(standings.map((d) => d.conference))];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        eyebrow={`${franchise.season.year} season · ${teams.length} teams`}
        title={franchise.league.name}
      >
        <Link href="/leagues" className="btn btn-ghost">
          My leagues
        </Link>
      </PageHeader>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-8">
          {conferences.map((conference) => (
            <section key={conference} aria-label={conference}>
              <h2 className="mb-3 font-display text-2xl font-bold uppercase tracking-wide">
                {conference}
              </h2>
              <div className="grid gap-6 md:grid-cols-2">
                {standings
                  .filter((d) => d.conference === conference)
                  .map((division) => (
                    <Panel key={division.division} title={division.division}>
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-[11px] uppercase tracking-wider text-mist">
                            <th className="pb-2 font-medium">Team</th>
                            <th className="pb-2 text-center font-medium">OVR</th>
                            <th className="pb-2 text-right font-medium">W-L</th>
                            <th className="hidden pb-2 text-right font-medium sm:table-cell">Cap</th>
                          </tr>
                        </thead>
                        <tbody>
                          {division.rows.map((row) => {
                            const detail = ratings.get(row.team.id);
                            const mine = row.team.id === franchise.team.id;
                            return (
                              <tr key={row.team.id} className="border-t border-white/5">
                                <td className="py-2">
                                  <span className={`flex items-center gap-2 ${mine ? "text-gold" : ""}`}>
                                    <TeamCrest team={row.team} size={20} />
                                    <span className="truncate">{row.team.full_name}</span>
                                    {detail && <TeamEditButton team={detail} />}
                                  </span>
                                </td>
                                <td className="py-2 text-center">
                                  {detail && <OvrBadge value={detail.ratings.overall} />}
                                </td>
                                <td className="py-2 text-right tabular-nums">{formatRecord(row)}</td>
                                <td className="hidden py-2 text-right tabular-nums text-mist sm:table-cell">
                                  {detail && formatMoney(detail.cap_space)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </Panel>
                  ))}
              </div>
            </section>
          ))}
        </div>

        <div className="space-y-6">
        <Panel title="Power rankings" className="h-fit">
          <ol className="space-y-1">
            {powerRanking.map((team, i) => (
              <li
                key={team.id}
                className={`flex items-center gap-3 rounded-md px-1.5 py-1 text-sm ${
                  team.id === franchise.team.id ? "bg-gold/10 text-gold" : ""
                }`}
              >
                <span className="stat-number w-5 text-right text-mist">{i + 1}</span>
                <TeamCrest team={team} size={18} />
                <span className="flex-1 truncate">{team.full_name}</span>
                <span className="text-xs tabular-nums text-mist">
                  {team.ratings.offense}/{team.ratings.defense}
                </span>
                <OvrBadge value={team.ratings.overall} />
              </li>
            ))}
          </ol>
        </Panel>
        <LeagueRulesPanel key={JSON.stringify(rules)} leagueId={franchise.league.id} initial={rules}
          commissioner={franchise.role === "commissioner"} />
        <FrontOffices offices={offices} />
        </div>
      </div>
    </div>
  );
}
