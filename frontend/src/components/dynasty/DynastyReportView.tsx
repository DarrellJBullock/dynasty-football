import Link from "next/link";
import { OffseasonRecap } from "@/components/dashboard/OffseasonRecap";
import { SeasonCard } from "@/components/history/HistoryView";
import type { DynastyReport, TeamSummary } from "@/lib/types";

/** Seasons at a glance, after a sim ahead (or from History): each season's result and
 * awards, then what the franchise's offseason after it did. */
export function DynastyReportView({ report, team, league }: {
  report: DynastyReport; team: TeamSummary; league: string;
}) {
  const titles = report.seasons.filter((s) => s.season.champion?.id === team.id).length;
  const wins = report.seasons.reduce((sum, s) => sum + (s.season.franchise_record?.wins ?? 0), 0);
  const losses = report.seasons.reduce((sum, s) => sum + (s.season.franchise_record?.losses ?? 0), 0);
  const span = report.from_year === report.to_year
    ? `${report.from_year}` : `${report.from_year}–${report.to_year}`;
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow text-gold">{league}</div>
          <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Dynasty report</h1>
          <p className="mt-1 text-sm text-mist">
            {span} · {report.seasons.length} season{report.seasons.length === 1 ? "" : "s"} ·{" "}
            {team.nickname} {wins}–{losses} · {titles} championship{titles === 1 ? "" : "s"}
          </p>
        </div>
        <Link href="/history" className="text-sm text-gold hover:underline">History →</Link>
      </div>
      {report.seasons.length === 0 && (
        <p className="panel p-6 text-sm text-mist">No finished seasons in {span}.</p>
      )}
      {report.seasons.map(({ season, offseason }) => (
        <div key={season.season_id} className="space-y-3">
          <SeasonCard season={season} team={team} />
          {offseason && <OffseasonRecap recap={offseason} />}
        </div>
      ))}
    </div>
  );
}
