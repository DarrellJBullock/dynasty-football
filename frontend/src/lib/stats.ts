/** Box-score column groups shared by the game page and player pages. */

export type Stats = Record<string, number>;

export interface StatGroup {
  title: string;
  /** Show this group for a player whose stats include any of these keys. */
  has: string[];
  sortBy: string;
  columns: [label: string, value: (s: Stats) => string | number][];
  /** Not one of the box score's top-five tables (the game page lists it on its own). */
  ownSection?: boolean;
}

const n = (s: Stats, key: string) => s[key] ?? 0;

export const STAT_GROUPS: StatGroup[] = [
  { title: "Passing", has: ["pass_att"], sortBy: "pass_att", columns: [
    ["C/ATT", (s) => `${n(s, "pass_cmp")}/${n(s, "pass_att")}`], ["YDS", (s) => n(s, "pass_yds")],
    ["TD", (s) => n(s, "pass_td")], ["INT", (s) => n(s, "pass_int")], ["SACK", (s) => n(s, "sacked")]] },
  { title: "Rushing", has: ["rush_att"], sortBy: "rush_yds", columns: [
    ["ATT", (s) => n(s, "rush_att")], ["YDS", (s) => n(s, "rush_yds")], ["TD", (s) => n(s, "rush_td")],
    ["LONG", (s) => n(s, "rush_long")]] },
  { title: "Receiving", has: ["targets"], sortBy: "rec_yds", columns: [
    ["REC", (s) => n(s, "receptions")], ["TGT", (s) => n(s, "targets")], ["YDS", (s) => n(s, "rec_yds")],
    ["TD", (s) => n(s, "rec_td")], ["LONG", (s) => n(s, "rec_long")]] },
  { title: "Defense", has: ["tackles", "sacks", "interceptions", "passes_defended"], sortBy: "tackles", columns: [
    ["TKL", (s) => n(s, "tackles")], ["SACK", (s) => n(s, "sacks")], ["INT", (s) => n(s, "interceptions")],
    ["PD", (s) => n(s, "passes_defended")], ["FF", (s) => n(s, "forced_fumbles")]] },
  { title: "Kicking", has: ["fg_att", "xp_att", "punts"], sortBy: "fg_att", columns: [
    ["FG", (s) => `${n(s, "fg_made")}/${n(s, "fg_att")}`], ["LONG", (s) => n(s, "fg_long")],
    ["XP", (s) => `${n(s, "xp_made")}/${n(s, "xp_att")}`], ["PUNTS", (s) => n(s, "punts")],
    ["AVG", (s) => (s.punts ? (s.punt_yds / s.punts).toFixed(1) : "–")]] },
  { title: "Snaps", has: ["snaps"], sortBy: "snaps", ownSection: true, columns: [
    ["SNAPS", (s) => n(s, "snaps")]] },
];

export function hasGroup(group: StatGroup, stats: Stats): boolean {
  return group.has.some((key) => (stats[key] ?? 0) > 0);
}

/** Groups to show for a player: the ones their stats actually touch. */
export function groupsFor(stats: Stats): StatGroup[] {
  return STAT_GROUPS.filter((g) => hasGroup(g, stats));
}

/** Human labels for leader-row supporting stats. */
export const STAT_LABELS: Record<string, string> = {
  pass_cmp: "CMP", pass_att: "ATT", pass_td: "TD", pass_int: "INT", pass_yds: "YDS",
  rush_att: "ATT", rush_td: "TD", rush_long: "LONG", rush_yds: "YDS",
  receptions: "REC", targets: "TGT", rec_td: "TD", rec_long: "LONG", rec_yds: "YDS",
  tackles: "TKL", sacks: "SACK", interceptions: "INT", forced_fumbles: "FF",
  passes_defended: "PD", int_return_yds: "RET YDS",
  fg_att: "FGA", fg_long: "LONG", xp_made: "XP", snaps: "SNAPS",
};

/** Each player's share of his unit's snaps: offense, or defense (from the busiest
 * player on each side, who played every snap the unit did). */
export function snapShares<T extends { position: string; stats: Stats }>(players: T[]):
    (T & { snaps: number; share: number })[] {
  const OFFENSE = new Set(["QB", "RB", "FB", "WR", "TE", "OT", "OG", "C"]);
  const unit = (p: T) => (OFFENSE.has(p.position) ? "offense" : "defense");
  const most = { offense: 0, defense: 0 };
  for (const p of players) most[unit(p)] = Math.max(most[unit(p)], p.stats.snaps ?? 0);
  return players
    .filter((p) => (p.stats.snaps ?? 0) > 0)
    .map((p) => ({ ...p, snaps: p.stats.snaps, share: p.stats.snaps / Math.max(1, most[unit(p)]) }));
}
