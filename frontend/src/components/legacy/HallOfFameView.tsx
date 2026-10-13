import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import type { HallOfFame, HallOfFamer } from "@/lib/types";

/** The Hall of Fame: every class, the latest ballot's near misses, and retired numbers. */
export function HallOfFameView({ hall, league }: { hall: HallOfFame; league: string }) {
  const classes = [...new Set(hall.members.map((m) => m.year))];
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader eyebrow={league} title="Hall of Fame">
        <p className="max-w-md text-sm text-mist">
          Retired players become eligible {hall.eligible_after} seasons after they retire. The best careers
          (production against everyone at the position, awards, titles, seasons) get in, a few a year.
        </p>
      </PageHeader>
      <div className="space-y-6">
        {classes.length === 0 ? (
          <Panel><p className="text-sm text-mist">No one yet. The first class is voted on after a player has been retired {hall.eligible_after} seasons.</p></Panel>
        ) : classes.map((year) => (
          <Panel key={year} title={`Class of ${year}`}>
            <ul className="grid gap-3 md:grid-cols-2" aria-label={`Class of ${year}`}>
              {hall.members.filter((m) => m.year === year).map((m) => <Famer key={m.player_id} famer={m} />)}
            </ul>
          </Panel>
        ))}
        {hall.near_misses.length > 0 && (
          <Panel title={`Close, in ${hall.ballot_year}`}>
            <p className="mb-3 text-sm text-mist">The best cases that didn&apos;t reach the bar ({hall.bar}). They stay eligible.</p>
            <ul className="grid gap-3 md:grid-cols-2" aria-label="Near misses">
              {hall.near_misses.map((m) => <Famer key={m.player_id} famer={m} />)}
            </ul>
          </Panel>
        )}
        {hall.retired_numbers.length > 0 && (
          <Panel title="Retired numbers">
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label="Retired numbers">
              {hall.retired_numbers.map((r) => (
                <li key={`${r.team.id}-${r.number}`} className="flex items-center gap-2 text-sm">
                  <TeamCrest team={r.team} size={20} />
                  <span className="stat-number w-8 text-lg">{r.number}</span>
                  <Link href={`/players/${r.player_id}`} className="hover:text-gold">{r.name}</Link>
                  <span className="ml-auto text-xs text-mist">{r.team.abbreviation} · {r.year}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

function Famer({ famer }: { famer: HallOfFamer }) {
  return (
    <li className="flex items-start gap-3 rounded-lg border border-white/5 p-3" aria-label={famer.name}>
      {famer.team ? <TeamCrest team={famer.team} size={32} /> : <span className="w-8" />}
      <div className="min-w-0 flex-1">
        <Link href={`/players/${famer.player_id}`} className="font-semibold hover:text-gold">
          <span className="mr-1.5 text-xs text-mist">{famer.position}</span>{famer.name}
        </Link>
        <p className="text-sm text-mist">{famer.case}</p>
        <p className="text-xs text-mist/70">
          {famer.team ? famer.team.full_name : "No team"}
          {famer.retired_year && ` · retired ${famer.retired_year}`}
        </p>
      </div>
      <span className="stat-number text-lg text-gold" title="Legacy score">{famer.score}</span>
    </li>
  );
}
