import type { DepthChart, DepthSlot, PlayerSummary, Position, Unit } from "@/lib/types";

export const SLOT_NAMES: Record<Position, string> = {
  QB: "Quarterback",
  RB: "Running Back",
  FB: "Fullback",
  WR: "Wide Receiver",
  TE: "Tight End",
  OT: "Offensive Tackle",
  OG: "Offensive Guard",
  C: "Center",
  DE: "Defensive End",
  DT: "Defensive Tackle",
  OLB: "Outside Linebacker",
  MLB: "Middle Linebacker",
  CB: "Cornerback",
  FS: "Free Safety",
  SS: "Strong Safety",
  K: "Kicker",
  P: "Punter",
};

export const UNITS: { unit: Unit; label: string }[] = [
  { unit: "offense", label: "Offense" },
  { unit: "defense", label: "Defense" },
  { unit: "special_teams", label: "Special Teams" },
];

/** Returns a new array with the item at `from` moved to index `to`. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= items.length) return [...items];
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, item);
  return next;
}

/** Map of player id -> the slot where that player is currently fielded as a starter. */
export function startingSlots(chart: DepthChart): Map<number, Position> {
  const result = new Map<number, Position>();
  for (const slot of chart.slots) {
    for (const id of slot.starter_ids) result.set(id, slot.slot);
  }
  return result;
}

export type RowStatus =
  | { kind: "starter" }
  | { kind: "injured" }
  | { kind: "starting-elsewhere"; slot: Position }
  | { kind: "backup" };

/**
 * Why a row is (or isn't) starting. Rows inside the starter window that aren't
 * fielded get an explanation, so the user understands the lineup.
 */
export function rowStatus(
  player: PlayerSummary,
  index: number,
  slot: DepthSlot,
  starters: Map<number, Position>,
): RowStatus {
  if (slot.starter_ids.includes(player.id)) return { kind: "starter" };
  if (index < slot.starters) {
    if (player.injury_status === "out" || player.injury_status === "injured_reserve") {
      return { kind: "injured" };
    }
    const elsewhere = starters.get(player.id);
    if (elsewhere && elsewhere !== slot.slot) return { kind: "starting-elsewhere", slot: elsewhere };
  }
  return { kind: "backup" };
}

/** Rostered players who could be added to a slot (anyone not already listed there). */
export function addablePlayers(chart: DepthChart, slot: DepthSlot): PlayerSummary[] {
  const listed = new Set(slot.players.map((p) => p.id));
  const roster = new Map<number, PlayerSummary>();
  for (const s of chart.slots) for (const p of s.players) roster.set(p.id, p);
  return [...roster.values()]
    .filter((p) => !listed.has(p.id))
    .sort((a, b) => a.position.localeCompare(b.position) || b.overall - a.overall);
}

export function replaceSlotOrder(chart: DepthChart, slot: Position, players: PlayerSummary[]): DepthChart {
  return {
    ...chart,
    slots: chart.slots.map((s) => (s.slot === slot ? { ...s, players, customized: true } : s)),
  };
}
