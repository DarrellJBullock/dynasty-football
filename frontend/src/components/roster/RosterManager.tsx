"use client";

import { useCallback, useMemo, useState } from "react";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import {
  DEFAULT_SORT,
  filterRoster,
  groupCounts,
  nextSort,
  sortRoster,
  type GroupFilter,
  type SortState,
} from "@/lib/roster";
import {
  POSITION_GROUPS,
  type PlayerCreate,
  type PlayerDetail,
  type PlayerSummary,
  type TeamDetail,
} from "@/lib/types";
import { AddPlayerDialog } from "./AddPlayerDialog";
import { FreeAgentsDialog } from "./FreeAgentsDialog";
import { PlayerPanel } from "./PlayerPanel";
import { RosterTable } from "./RosterTable";

const GROUP_TABS: GroupFilter[] = ["ALL", ...POSITION_GROUPS];

/** PlayerDetail is a superset of PlayerSummary; drop the full ratings map for list state. */
function toSummary(player: PlayerDetail): PlayerSummary {
  const { ratings, ...summary } = player;
  void ratings;
  return summary;
}

export function RosterManager({
  initialTeam,
  initialRoster,
  leagueId,
  seasonYear,
}: {
  initialTeam: TeamDetail;
  initialRoster: PlayerSummary[];
  leagueId: number;
  seasonYear: number;
}) {
  const [team, setTeam] = useState(initialTeam);
  const [roster, setRoster] = useState(initialRoster);
  const [group, setGroup] = useState<GroupFilter>("ALL");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(DEFAULT_SORT);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [dialog, setDialog] = useState<"free-agents" | "add" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const visible = useMemo(
    () => sortRoster(filterRoster(roster, group, search), sort),
    [roster, group, search, sort],
  );
  const counts = useMemo(() => groupCounts(roster), [roster]);
  const rosterFull = roster.length >= team.roster_max;

  const refreshTeam = useCallback(async () => {
    try {
      setTeam(await api.team(team.id));
    } catch {
      // Team header is informational; a failed refresh shouldn't break the screen.
    }
  }, [team.id]);

  const handleUpdated = useCallback(
    (player: PlayerDetail) => {
      setRoster((current) => current.map((p) => (p.id === player.id ? toSummary(player) : p)));
      setNotice(`Saved ${player.full_name}.`);
      void refreshTeam();
    },
    [refreshTeam],
  );

  const handleReleased = useCallback(
    (player: PlayerDetail) => {
      setRoster((current) => current.filter((p) => p.id !== player.id));
      setSelectedId(null);
      setNotice(`${player.full_name} was released and is now a free agent.`);
      void refreshTeam();
    },
    [refreshTeam],
  );

  async function handleSign(player: PlayerSummary) {
    const signed = await api.signPlayer(team.id, player.id);
    setRoster((current) => [...current, toSummary(signed)]);
    setNotice(`Signed ${signed.full_name} (#${signed.jersey_number}).`);
    await refreshTeam();
  }

  async function handleCreate(payload: PlayerCreate) {
    const created = await api.createPlayer(team.id, payload);
    setRoster((current) => [...current, toSummary(created)]);
    setDialog(null);
    setSelectedId(created.id);
    setNotice(`Created ${created.full_name}.`);
    await refreshTeam();
  }

  const closePanel = useCallback(() => setSelectedId(null), []);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-4">
          <TeamCrest team={team} size={52} />
          <div>
            <div className="eyebrow text-gold">Roster management</div>
            <h1 className="font-display text-4xl font-bold uppercase tracking-wide">
              {team.full_name}
            </h1>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn btn-ghost" onClick={() => setDialog("free-agents")}>
            Free agents
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={rosterFull}
            title={rosterFull ? "Roster is full — release a player first" : undefined}
            onClick={() => setDialog("add")}
          >
            + Create player
          </button>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Summary label="Team OVR">
          <OvrBadge value={team.ratings.overall} size="md" />
        </Summary>
        <Summary label="Roster">
          <span className={rosterFull ? "" : "text-amber-300"} data-testid="roster-count">
            {roster.length}
          </span>
          <span className="text-mist">/{team.roster_max}</span>
        </Summary>
        <Summary label="Payroll">{formatMoney(team.payroll)}</Summary>
        <Summary label="Cap space">
          <span className={team.cap_space < 0 ? "text-rose-300" : "text-emerald-300"}>
            {formatMoney(team.cap_space)}
          </span>
        </Summary>
      </dl>

      {notice && (
        <div
          role="status"
          className="flex items-center justify-between rounded-lg border border-emerald-400/20 bg-emerald-400/5 px-4 py-2 text-sm text-emerald-200"
        >
          {notice}
          <button type="button" className="text-emerald-200/60 hover:text-emerald-100" onClick={() => setNotice(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 p-3">
          <div role="tablist" aria-label="Position group" className="flex flex-wrap gap-1">
            {GROUP_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={group === tab}
                onClick={() => setGroup(tab)}
                className={`rounded-md px-2.5 py-1.5 font-display text-sm font-semibold tracking-wide transition-colors ${
                  group === tab ? "bg-gold text-ink-950" : "text-mist hover:bg-white/5 hover:text-chalk"
                }`}
              >
                {tab === "ALL" ? "All" : tab}
                <span className={`ml-1.5 text-xs ${group === tab ? "text-ink-950/60" : "text-mist/60"}`}>
                  {counts[tab] ?? 0}
                </span>
              </button>
            ))}
          </div>
          <input
            type="search"
            placeholder="Search name, position, #"
            aria-label="Search roster"
            className="field-input w-full sm:w-64"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <RosterTable
          players={visible}
          sort={sort}
          onSort={(key) => setSort((s) => nextSort(s, key))}
          selectedId={selectedId}
          onSelect={setSelectedId}
          seasonYear={seasonYear}
        />
      </section>

      {selectedId !== null && (
        <PlayerPanel
          playerId={selectedId}
          seasonYear={seasonYear}
          onClose={closePanel}
          onUpdated={handleUpdated}
          onReleased={handleReleased}
        />
      )}
      {dialog === "free-agents" && (
        <FreeAgentsDialog
          leagueId={leagueId}
          rosterFull={rosterFull}
          onSign={handleSign}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "add" && (
        <AddPlayerDialog onCreate={handleCreate} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}

function Summary({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="panel flex items-center justify-between px-4 py-3">
      <dt className="eyebrow">{label}</dt>
      <dd className="stat-number text-2xl">{children}</dd>
    </div>
  );
}
