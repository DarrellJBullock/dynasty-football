import Link from "next/link";
import { FieldPreviewLoader } from "@/components/field/FieldPreviewLoader";
import { SimControls } from "@/components/season/SimControls";
import { TurnPanel } from "@/components/season/TurnPanel";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { Panel } from "@/components/ui/Panel";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { formatMoney, formatPhase, formatRecord, injuryDetail, injuryLabel, type InjurySeason, ratingTier, TIER_BAR } from "@/lib/format";
import { gameLabel, OUTCOME_STYLES, resultFor } from "@/lib/games";
import { OffseasonRecap } from "./OffseasonRecap";
import type { Alert, Dashboard, Game, PlayerSummary, PositionGroupSummary, TeamSummary } from "@/lib/types";

export function DashboardView({ data }: { data: Dashboard }) {
  const { franchise, team, record } = data;
  const nextGame = data.upcoming_games[0];
  const opponent = nextGame && (nextGame.home.id === team.id ? nextGame.away : nextGame.home);

  return (
    <div
      className="mx-auto max-w-7xl space-y-6"
      style={
        {
          "--team-primary": team.primary_color,
          "--team-secondary": team.secondary_color,
        } as React.CSSProperties
      }
    >
      <Hero data={data} awayColor={opponent?.primary_color ?? "#3a4a5e"}
        awayAccent={opponent?.secondary_color ?? "#e5e7eb"} />

      {data.offseason && <OffseasonRecap recap={data.offseason} />}

      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        <NextGameCard game={nextGame} teamId={team.id} />
        <CapCard payroll={team.payroll} capSpace={team.cap_space} cap={franchise.league.salary_cap}
          dead={team.dead_money ?? 0} />
        <RosterCard
          count={team.roster_count}
          max={team.roster_max}
          expiring={data.expiring_contracts}
        />
        <RecordCard record={record} division={data.division_standings.division} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title="Top players"
          className="lg:col-span-1"
          action={
            <Link href="/roster" className="text-xs text-gold hover:underline">
              Full roster →
            </Link>
          }
        >
          <ol className="space-y-1">
            {data.top_players.map((player, i) => (
              <li
                key={player.id}
                className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
              >
                <span className="stat-number w-4 text-sm text-mist">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <Link href={`/players/${player.id}`} className="block truncate text-sm font-medium hover:text-gold">
                    {player.full_name}
                  </Link>
                  <div className="text-xs text-mist">
                    {player.position} · #{player.jersey_number} · Age {player.age}
                  </div>
                </div>
                <OvrBadge value={player.overall} size="md" />
              </li>
            ))}
          </ol>
        </Panel>

        <Panel title="Unit strength" className="lg:col-span-1">
          <PositionGroups groups={data.position_groups} />
        </Panel>

        <div className="space-y-6 lg:col-span-1">
          <Panel title={`${data.division_standings.division} standings`}>
            <StandingsMini rows={data.division_standings.rows} teamId={team.id} />
          </Panel>
          <Panel title="Front office">
            <Alerts alerts={data.alerts} />
          </Panel>
          <Panel title="Injury report">
            <InjuryReport players={data.injury_report ?? []} season={data.franchise.season} />
          </Panel>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Panel
          title="Recent results"
          action={
            <Link href="/schedule" className="text-xs text-gold hover:underline">
              Schedule →
            </Link>
          }
        >
          <RecentResults games={data.recent_games} team={team} />
        </Panel>
        <Panel title="Upcoming schedule">
          <Schedule games={data.upcoming_games} team={team} />
        </Panel>
      </div>
    </div>
  );
}

function Hero({ data, awayColor, awayAccent }: {
  data: Dashboard; awayColor: string; awayAccent: string;
}) {
  const { franchise, team, record } = data;
  const units: [string, number][] = [
    ["Offense", team.ratings.offense],
    ["Defense", team.ratings.defense],
    ["Special Teams", team.ratings.special_teams],
  ];
  return (
    <section className="panel relative overflow-hidden" aria-label="Franchise overview">
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(700px 300px at 0% 0%, color-mix(in srgb, var(--team-primary) 55%, transparent), transparent 70%)",
        }}
      />
      <div className="relative grid gap-6 p-6 md:p-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="flex min-w-0 flex-col justify-between gap-8">
          <div>
            <div className="eyebrow text-gold">
              {franchise.name} · {franchise.season.year} {formatPhase(franchise.season.phase)}
            </div>
            <div className="mt-4 flex items-center gap-5">
              <TeamCrest team={team} size={72} />
              <div className="min-w-0">
                <div className="font-display text-xl font-semibold uppercase tracking-wide text-mist">
                  {team.city}
                </div>
                <h1 className="font-display text-4xl font-extrabold uppercase leading-none tracking-wide break-words sm:text-5xl 2xl:text-6xl">
                  {team.nickname}
                </h1>
                <div className="mt-2 text-sm text-mist">
                  {team.division} · {team.stadium}
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-x-8 gap-y-5">
            <div>
              <div className="eyebrow">Team OVR</div>
              <div className="mt-2">
                <OvrBadge value={team.ratings.overall} size="lg" />
              </div>
            </div>
            <div>
              <div className="eyebrow">Record</div>
              <div className="stat-number mt-2 text-5xl">{formatRecord(record)}</div>
            </div>
            <div className="min-w-48 flex-1 space-y-2.5">
              {units.map(([label, value]) => (
                <div key={label} className="flex items-center gap-3">
                  <span className="w-24 text-xs text-mist">{label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
                    <div
                      className={`h-full rounded-full ${TIER_BAR[ratingTier(value)]}`}
                      style={{ width: `${value}%` }}
                    />
                  </div>
                  <span className="stat-number w-6 text-right text-base">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="relative h-64 overflow-hidden rounded-xl border border-white/5 bg-ink-950/60 md:h-80">
          <FieldPreviewLoader
            homeColor={team.primary_color}
            homeAccent={team.secondary_color}
            awayColor={awayColor}
            awayAccent={awayAccent}
            nickname={team.nickname}
            abbreviation={team.abbreviation}
          />
          <div className="eyebrow pointer-events-none absolute bottom-3 left-4 text-[10px]">
            {team.stadium}
          </div>
        </div>
      </div>
      <div className="relative border-t border-white/5 px-6 py-4 md:px-8">
        <TurnPanel leagueId={franchise.league.id} />
        <SimControls season={franchise.season} teamId={team.id}
          canRun={franchise.role === "commissioner"} />
      </div>
    </section>
  );
}

function StatCard({
  label,
  children,
  footer,
}: {
  label: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <section className="panel flex flex-col justify-between gap-4 p-5" aria-label={label}>
      <div className="eyebrow">{label}</div>
      <div>{children}</div>
      {footer && <div className="text-xs text-mist">{footer}</div>}
    </section>
  );
}

function NextGameCard({ game, teamId }: { game?: Game; teamId: number }) {
  if (!game) {
    return (
      <StatCard label="Next game">
        <div className="text-sm text-mist">No games scheduled.</div>
      </StatCard>
    );
  }
  const home = game.home.id === teamId;
  const opponent = home ? game.away : game.home;
  return (
    <StatCard label="Next game"
      footer={`${gameLabel(game)} · ${game.neutral_site ? "Neutral site" : home ? "Home" : "Away"}`}>
      <div className="flex items-center gap-3">
        <TeamCrest team={opponent} size={36} />
        <div className="min-w-0">
          <div className="text-xs text-mist">{home ? "vs" : "@"}</div>
          <div className="font-display text-xl font-bold uppercase leading-tight">
            {opponent.full_name}
          </div>
        </div>
        <Link href={`/games/${game.id}/coach`} className="btn btn-primary ml-auto shrink-0 px-3 py-1 text-xs">
          Coach this game
        </Link>
      </div>
    </StatCard>
  );
}

function CapCard({ payroll, capSpace, cap, dead }: {
  payroll: number; capSpace: number; cap: number; dead: number;
}) {
  const used = Math.min(100, (payroll / cap) * 100);
  const footer = `${formatMoney(payroll)} of ${formatMoney(cap)} committed` +
    (dead > 0 ? ` · incl. ${formatMoney(dead)} dead money` : "");
  return (
    <StatCard label="Salary cap" footer={footer}>
      <div className={`stat-number text-4xl ${capSpace < 0 ? "text-rose-300" : ""}`}>
        {formatMoney(capSpace)}
        <span className="ml-2 font-sans text-xs font-normal text-mist">space</span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
        <div
          className={`h-full rounded-full ${used > 97 ? "bg-rose-400" : "bg-gold"}`}
          style={{ width: `${used}%` }}
        />
      </div>
    </StatCard>
  );
}

function RosterCard({ count, max, expiring }: { count: number; max: number; expiring: number }) {
  return (
    <StatCard label="Active roster" footer={`${expiring} contracts expiring after this season`}>
      <div className="stat-number text-4xl">
        {count}
        <span className="text-2xl text-mist">/{max}</span>
      </div>
    </StatCard>
  );
}

function RecordCard({
  record,
  division,
}: {
  record: Dashboard["record"];
  division: string;
}) {
  const games = record.wins + record.losses + record.ties;
  return (
    <StatCard label="Season" footer={games ? `${division} race` : "Preseason — no games played"}>
      <div className="stat-number text-4xl">{formatRecord(record)}</div>
    </StatCard>
  );
}

function PositionGroups({ groups }: { groups: PositionGroupSummary[] }) {
  return (
    <ul className="space-y-3">
      {groups.map((g) => (
        <li key={g.group} className="grid grid-cols-[2.5rem_minmax(0,1fr)_2rem] items-center gap-3">
          <span className="font-display text-sm font-semibold">{g.group}</span>
          <div className="relative h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-white/15"
              style={{ width: `${g.average_overall}%` }}
              title={`Group average ${g.average_overall}`}
            />
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${TIER_BAR[ratingTier(g.starter_overall)]}`}
              style={{ width: `${g.starter_overall}%`, opacity: 0.85 }}
              title={`Starters ${g.starter_overall}`}
            />
          </div>
          <span className="stat-number text-right text-sm">{g.starter_overall}</span>
        </li>
      ))}
      <li className="pt-1 text-[11px] text-mist">Bar: starters · faded: full group average</li>
    </ul>
  );
}

function StandingsMini({ rows, teamId }: { rows: Dashboard["division_standings"]["rows"]; teamId: number }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wider text-mist">
          <th className="pb-2 font-medium">Team</th>
          <th className="pb-2 text-right font-medium">W-L</th>
          <th className="pb-2 text-right font-medium">PF</th>
          <th className="pb-2 text-right font-medium">PA</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.team.id}
            className={`border-t border-white/5 ${row.team.id === teamId ? "text-gold" : ""}`}
          >
            <td className="py-2">
              <span className="flex items-center gap-2">
                <TeamCrest team={row.team} size={18} />
                {row.team.full_name}
              </span>
            </td>
            <td className="py-2 text-right tabular-nums">{formatRecord(row)}</td>
            <td className="py-2 text-right tabular-nums text-mist">{row.points_for}</td>
            <td className="py-2 text-right tabular-nums text-mist">{row.points_against}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const ALERT_STYLES: Record<Alert["level"], string> = {
  info: "bg-sky-400",
  warning: "bg-amber-400",
  critical: "bg-rose-400",
};

function Alerts({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return <p className="text-sm text-mist">All clear.</p>;
  return (
    <ul className="space-y-2.5">
      {alerts.map((alert) => (
        <li key={alert.message} className="flex items-start gap-3 text-sm">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${ALERT_STYLES[alert.level]}`} />
          <span className="text-chalk/90">{alert.message}</span>
        </li>
      ))}
    </ul>
  );
}

function InjuryReport({ players, season }: { players: PlayerSummary[]; season: InjurySeason }) {
  if (!players.length) return <p className="text-sm text-mist">Everyone is healthy.</p>;
  return (
    <ul className="space-y-2" aria-label="Injured players">
      {players.map((player) => (
        <li key={player.id} className="flex items-center gap-3 text-sm">
          <span className="w-8 shrink-0 rounded bg-rose-500/15 text-center text-[10px] font-semibold uppercase text-rose-300">
            {injuryLabel(player.injury_status)}
          </span>
          <div className="min-w-0 flex-1">
            <Link href={`/players/${player.id}`} className="block truncate hover:text-gold">
              <span className="mr-1.5 text-xs text-mist">{player.position}</span>
              {player.full_name}
            </Link>
            <div className="truncate text-xs text-mist">{injuryDetail(player, season)}</div>
          </div>
          <OvrBadge value={player.overall} />
        </li>
      ))}
    </ul>
  );
}

function Schedule({ games, team }: { games: Game[]; team: TeamSummary }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {games.map((game) => {
        const home = game.home.id === team.id;
        const opponent = home ? game.away : game.home;
        return (
          <li key={game.id}>
            <Link
              href={`/games/${game.id}`}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 hover:border-white/15"
            >
              <TeamCrest team={opponent} size={28} />
              <div className="min-w-0">
                <div className="eyebrow text-[10px]">{gameLabel(game)}</div>
                <div className="truncate text-sm font-medium">
                  {home ? "vs " : "@ "}
                  {opponent.nickname}
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function RecentResults({ games, team }: { games: Game[]; team: TeamSummary }) {
  if (!games.length) {
    return <p className="text-sm text-mist">No games played yet. Sim a week to get started.</p>;
  }
  return (
    <ul className="space-y-2">
      {games.map((game) => {
        const r = resultFor(game, team.id);
        return (
          <li key={game.id}>
            <Link
              href={`/games/${game.id}`}
              className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]"
            >
              <span className={`stat-number w-6 rounded text-center text-sm ${OUTCOME_STYLES[r.outcome ?? "T"]}`}>
                {r.outcome}
              </span>
              <TeamCrest team={r.opponent} size={22} />
              <span className="min-w-0 flex-1 truncate text-sm">
                {r.home ? "vs" : "@"} {r.opponent.nickname}
              </span>
              <span className="stat-number text-base tabular-nums">
                {r.pointsFor}-{r.pointsAgainst}
                {game.overtime && <span className="ml-1 text-xs text-mist">OT</span>}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
