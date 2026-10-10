import type { PlayerSummary, PositionGroup } from "@/lib/types";

export type GroupFilter = PositionGroup | "ALL";

export type SortKey =
  | "jersey_number" | "last_name" | "position" | "overall" | "potential" | "age" | "salary";

export interface SortState {
  key: SortKey;
  direction: "asc" | "desc";
}

export const DEFAULT_SORT: SortState = { key: "overall", direction: "desc" };

// Offense -> defense -> specialists, the order a depth chart reads.
const POSITION_ORDER = [
  "QB", "RB", "FB", "WR", "TE", "OT", "OG", "C",
  "DE", "DT", "OLB", "MLB", "CB", "FS", "SS", "K", "P",
];

function sortValue(player: PlayerSummary, key: SortKey): number | string {
  switch (key) {
    case "salary":
      return player.contract?.salary ?? 0;
    case "position":
      return POSITION_ORDER.indexOf(player.position);
    case "last_name":
      return `${player.last_name} ${player.first_name}`.toLowerCase();
    default:
      return player[key];
  }
}

export function filterRoster(
  players: PlayerSummary[],
  group: GroupFilter,
  search: string,
): PlayerSummary[] {
  const query = search.trim().toLowerCase();
  return players.filter((p) => {
    if (group !== "ALL" && p.position_group !== group) return false;
    if (!query) return true;
    return (
      p.full_name.toLowerCase().includes(query) ||
      p.position.toLowerCase() === query ||
      String(p.jersey_number) === query
    );
  });
}

export function sortRoster(players: PlayerSummary[], sort: SortState): PlayerSummary[] {
  const factor = sort.direction === "asc" ? 1 : -1;
  return [...players].sort((a, b) => {
    const av = sortValue(a, sort.key);
    const bv = sortValue(b, sort.key);
    if (av < bv) return -1 * factor;
    if (av > bv) return 1 * factor;
    return b.overall - a.overall || a.id - b.id; // stable, best player first
  });
}

/** Clicking the active column flips direction; a new column starts with its natural order. */
export function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key === key) {
    return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  const ascending: SortKey[] = ["jersey_number", "last_name", "position", "age"];
  return { key, direction: ascending.includes(key) ? "asc" : "desc" };
}

export function groupCounts(players: PlayerSummary[]): Record<GroupFilter, number> {
  const counts = { ALL: players.length } as Record<GroupFilter, number>;
  for (const p of players) counts[p.position_group] = (counts[p.position_group] ?? 0) + 1;
  return counts;
}
