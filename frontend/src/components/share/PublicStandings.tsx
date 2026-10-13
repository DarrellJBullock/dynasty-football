import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatPhase, formatRecord } from "@/lib/format";
import type { Site } from "@/lib/site";
import type { DivisionStandings, PublicLeague } from "@/lib/types";

/** A public link's front page: the league and its standings. */
export function PublicStandings({ home, standings, site }: {
  home: PublicLeague; standings: DivisionStandings[]; site: Site;
}) {
  const conferences = [...new Set(standings.map((d) => d.conference))];
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader eyebrow={`${home.season.year} ${formatPhase(home.season.phase)} · ${home.teams.length} teams`}
        title={home.league.name}>
        <Link href={`${site.base}/schedule`} className="btn btn-ghost">This week&apos;s games</Link>
      </PageHeader>
      {home.season.champion && (
        <p className="mb-6 flex items-center gap-2 text-sm text-gold">
          <TeamCrest team={home.season.champion} size={20} />
          {home.season.year} champion: {home.season.champion.full_name}
        </p>
      )}
      <div className="space-y-8">
        {conferences.map((conference) => (
          <section key={conference} aria-label={conference} className="space-y-4">
            <h2 className="eyebrow">{conference}</h2>
            <div className="grid gap-6 md:grid-cols-2">
              {standings.filter((d) => d.conference === conference).map((division) => (
                <Panel key={division.division} title={division.division}>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wider text-mist">
                        <th className="py-1 font-medium">Team</th>
                        <th className="text-right font-medium">Record</th>
                        <th className="text-right font-medium">PF</th>
                        <th className="text-right font-medium">PA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {division.rows.map((row) => (
                        <tr key={row.team.id} className="border-t border-white/5">
                          <td className="py-1.5">
                            <span className="flex items-center gap-2">
                              <TeamCrest team={row.team} size={20} /> {row.team.full_name}
                            </span>
                          </td>
                          <td className="text-right tabular-nums">{formatRecord(row)}</td>
                          <td className="text-right tabular-nums text-mist">{row.points_for}</td>
                          <td className="text-right tabular-nums text-mist">{row.points_against}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Panel>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
