/**
 * Running game stats for the broadcast's stat overlays (docs/design/broadcast.md §3):
 * player and team lines folded from the play events up to a play, by the same rules as the
 * backend's box scores (backend/app/sim/stats.py), plus drive summaries and the stat line a
 * notable play earns. Pure.
 */

import type { PlaybackPlay, PlaybackPlayer } from "@/lib/types";
import { highlightReason } from "@/lib/highlights";

export interface PlayerLine {
  pass_att: number; pass_cmp: number; pass_yds: number; pass_td: number; pass_int: number;
  rush_att: number; rush_yds: number; rush_td: number;
  receptions: number; rec_yds: number; rec_td: number;
  tackles: number; sacks: number; interceptions: number;
}

export interface TeamLine {
  plays: number; total_yds: number; pass_yds: number; rush_yds: number; first_downs: number;
  third_down_att: number; third_down_conv: number; turnovers: number; time_of_possession: number;
}

type Side = "home" | "away";

const emptyPlayer = (): PlayerLine => ({
  pass_att: 0, pass_cmp: 0, pass_yds: 0, pass_td: 0, pass_int: 0, rush_att: 0, rush_yds: 0,
  rush_td: 0, receptions: 0, rec_yds: 0, rec_td: 0, tackles: 0, sacks: 0, interceptions: 0,
});
const emptyTeam = (): TeamLine => ({
  plays: 0, total_yds: 0, pass_yds: 0, rush_yds: 0, first_downs: 0, third_down_att: 0,
  third_down_conv: 0, turnovers: 0, time_of_possession: 0,
});

export interface GameStats {
  players: Map<number, PlayerLine>;
  teams: Record<Side, TeamLine>;
}

/** Stats through play `through` (an index into `plays`, inclusive). */
export function statsThrough(plays: PlaybackPlay[], through: number): GameStats {
  const players = new Map<number, PlayerLine>();
  const teams: Record<Side, TeamLine> = { home: emptyTeam(), away: emptyTeam() };
  const p = (id: number | null | undefined): PlayerLine => {
    if (id == null) return emptyPlayer(); // (never stored)
    let line = players.get(id);
    if (!line) players.set(id, line = emptyPlayer());
    return line;
  };
  for (const play of plays.slice(0, through + 1)) {
    const off = play.side;
    const team = teams[off];
    const result = play.result;
    if (play.down != null) team.time_of_possession += play.elapsed;
    if (play.down != null && ["run", "pass", "sack", "scramble"].includes(result.type)) {
      team.plays += 1;
      if (play.down === 3) {
        team.third_down_att += 1;
        if (result.first_down || result.touchdown) team.third_down_conv += 1;
      }
    }
    if (result.first_down || (result.touchdown && play.down != null)) team.first_downs += 1;
    if (result.turnover) team.turnovers += 1;
    if (result.type === "penalty") continue; // the action was nullified or replaced by the foul
    for (const e of play.events) {
      if (e.t === "rush" || e.t === "scramble" || e.t === "kneel") {
        const line = p(e.t === "rush" ? e.player : e.qb);
        line.rush_att += 1;
        line.rush_yds += e.yards;
        team.rush_yds += e.yards;
        team.total_yds += e.yards;
        if (e.t !== "kneel" && result.touchdown) line.rush_td += 1;
      } else if (e.t === "sack") {
        const by = p(e.by);
        by.sacks += 1;
        by.tackles += 1;
        team.pass_yds += e.yards;
        team.total_yds += e.yards;
      } else if (e.t === "pass") {
        const qb = p(e.qb);
        qb.pass_att += 1;
        if (e.result === "complete") {
          const receiver = p(e.target);
          qb.pass_cmp += 1;
          qb.pass_yds += e.yards;
          receiver.receptions += 1;
          receiver.rec_yds += e.yards;
          team.pass_yds += e.yards;
          team.total_yds += e.yards;
          if (result.touchdown) {
            qb.pass_td += 1;
            receiver.rec_td += 1;
          }
        } else if (e.result === "interception") {
          qb.pass_int += 1;
        }
      } else if (e.t === "interception") {
        p(e.by).interceptions += 1;
      } else if (e.t === "tackle") {
        for (const id of e.by) p(id).tackles += 1;
      }
    }
  }
  // Stand-ins (negative ids) are never credited.
  for (const id of [...players.keys()]) if (id < 0) players.delete(id);
  return { players, teams };
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function passing(l: PlayerLine): string {
  return [`${l.pass_cmp}/${l.pass_att}`, `${l.pass_yds} yds`, l.pass_td && `${l.pass_td} TD`,
          l.pass_int && `${l.pass_int} INT`].filter(Boolean).join(", ");
}
function rushing(l: PlayerLine): string {
  return [`${l.rush_att} car`, `${l.rush_yds} yds`, l.rush_td && `${l.rush_td} TD`].filter(Boolean).join(", ");
}
function receiving(l: PlayerLine): string {
  return [`${l.receptions} rec`, `${l.rec_yds} yds`, l.rec_td && `${l.rec_td} TD`].filter(Boolean).join(", ");
}
function defending(l: PlayerLine): string {
  return [l.tackles && plural(l.tackles, "tackle"), l.sacks && plural(l.sacks, "sack"),
          l.interceptions && `${l.interceptions} INT`].filter(Boolean).join(", ");
}

export interface StatLower { player: PlaybackPlayer | null; id: number; line: string }

/**
 * The stat line a notable play (a highlight or a sack) puts up, for its key player: the
 * passer on a touchdown pass, the receiver on another big catch, the runner on a big run or
 * a rushing touchdown, the defender on an interception or a sack.
 */
export function statLowerThird(plays: PlaybackPlay[], index: number,
                               roster: Map<number, PlaybackPlayer>): StatLower | null {
  const play = plays[index];
  if (!play || play.result.type === "penalty") return null;
  const sack = play.events.find((e) => e.t === "sack");
  if (!highlightReason(play, plays[index - 1]) && !sack) return null;
  const stats = statsThrough(plays, index);
  const show = (id: number, line: (l: PlayerLine) => string): StatLower | null =>
    id < 0 ? null : { id, player: roster.get(id) ?? null, line: line(stats.players.get(id) ?? emptyPlayer()) };
  const pick = play.events.find((e) => e.t === "interception");
  if (pick) return show(pick.by, defending);
  if (sack) return show(sack.by, defending);
  const pass = play.events.find((e) => e.t === "pass");
  if (pass && pass.result === "complete" && pass.target != null) {
    return play.result.touchdown ? show(pass.qb, passing) : show(pass.target, receiving);
  }
  const run = play.events.find((e) => e.t === "rush" || e.t === "scramble");
  if (run) return show(run.t === "rush" ? run.player : run.qb, rushing);
  return null;
}

export interface DriveSummary { side: Side; plays: number; yards: number; seconds: number; result: string }

const RESULTS: [(p: PlaybackPlay) => boolean, string][] = [
  [(p) => !!p.result.touchdown, "Touchdown"],
  [(p) => !!p.result.safety, "Safety"],
  [(p) => p.events.some((e) => e.t === "field_goal" && e.good), "Field goal"],
  [(p) => p.events.some((e) => e.t === "field_goal" && !e.good), "Missed field goal"],
  [(p) => p.events.some((e) => e.t === "punt"), "Punt"],
  [(p) => p.events.some((e) => e.t === "interception"), "Interception"],
  [(p) => p.events.some((e) => e.t === "fumble" && e.lost), "Fumble"],
  [(p) => !!p.result.turnover_on_downs, "Turnover on downs"],
];

/**
 * If play `index` ends a drive (the next snap belongs to the other team, or comes after a
 * kickoff, or the half or game ends), the drive's summary; otherwise null.
 */
export function driveEndingAt(plays: PlaybackPlay[], index: number): DriveSummary | null {
  const play = plays[index];
  if (!play || play.down == null) return null;
  const next = plays[index + 1];
  const halfOver = !next || (play.quarter === 2 && next.quarter >= 3) || (play.quarter >= 4 && next.quarter > play.quarter);
  const continues = next && next.down != null && next.side === play.side && !halfOver;
  if (continues) return null;
  let start = index;
  while (start > 0 && plays[start - 1].down != null && plays[start - 1].side === play.side) start -= 1;
  const drive = plays.slice(start, index + 1);
  const snaps = drive.filter((p) => p.result.type !== "penalty" || p.result.nullified);
  const from = drive[0].ball_on ?? 0;
  const lastSpot = play.result.touchdown ? 100 : (play.ball_on ?? from) + (Number(play.result.yards) || 0);
  const ending = RESULTS.find(([test]) => test(play))?.[1] ?? (halfOver ? (next ? "End of half" : "End of game") : "Downs");
  return {
    side: play.side, plays: snaps.length,
    yards: ending === "Punt" || ending.startsWith("Missed") || ending === "Field goal"
      ? (play.ball_on ?? from) - from : lastSpot - from,
    seconds: drive.reduce((sum, p) => sum + p.elapsed, 0), result: ending,
  };
}

/** "halftime" after the last play of the 2nd quarter, "final" after the last play. */
export function breakAfter(plays: PlaybackPlay[], index: number): "halftime" | "final" | null {
  const play = plays[index];
  if (!play) return null;
  if (index === plays.length - 1) return "final";
  return play.quarter === 2 && plays[index + 1].quarter >= 3 ? "halftime" : null;
}
