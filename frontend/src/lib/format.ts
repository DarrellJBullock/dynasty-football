/** $1.25M / $850K / $0 — compact money for dashboards and tables. */
export function formatMoney(dollars: number): string {
  const sign = dollars < 0 ? "-" : "";
  const abs = Math.abs(dollars);
  if (abs >= 1_000_000) {
    const millions = abs / 1_000_000;
    return `${sign}$${millions >= 100 ? millions.toFixed(0) : millions.toFixed(1)}M`;
  }
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}K`;
  return `${sign}$${abs}`;
}

/** 74 -> 6'2" */
export function formatHeight(inches: number): string {
  return `${Math.floor(inches / 12)}'${inches % 12}"`;
}

export function formatRecord(record: { wins: number; losses: number; ties: number }): string {
  const base = `${record.wins}-${record.losses}`;
  return record.ties ? `${base}-${record.ties}` : base;
}

/** "ball_carrier_vision" -> "Ball Carrier Vision" */
export function formatAttribute(name: string): string {
  return name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** "regular_season" -> "Regular Season" */
export const formatPhase = formatAttribute;

export type RatingTier = "elite" | "great" | "good" | "average" | "poor";

export function ratingTier(value: number): RatingTier {
  if (value >= 90) return "elite";
  if (value >= 80) return "great";
  if (value >= 70) return "good";
  if (value >= 60) return "average";
  return "poor";
}

/** Tailwind classes for a rating chip, keyed by tier. */
export const TIER_STYLES: Record<RatingTier, string> = {
  elite: "bg-amber-400/15 text-amber-300 ring-amber-400/40",
  great: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/40",
  good: "bg-sky-400/15 text-sky-300 ring-sky-400/40",
  average: "bg-slate-400/10 text-slate-300 ring-slate-400/30",
  poor: "bg-rose-400/10 text-rose-300 ring-rose-400/30",
};

/** Bar fill colour for a rating, matching TIER_STYLES. */
export const TIER_BAR: Record<RatingTier, string> = {
  elite: "bg-amber-400",
  great: "bg-emerald-400",
  good: "bg-sky-400",
  average: "bg-slate-400",
  poor: "bg-rose-400",
};

export function injuryLabel(status: string): string {
  return status === "injured_reserve" ? "IR" : formatAttribute(status);
}

/** Contract years remaining including the current season. */
export function yearsRemaining(endYear: number, currentYear: number): number {
  return Math.max(0, endYear - currentYear + 1);
}
