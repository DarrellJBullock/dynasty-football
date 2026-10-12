"use client";

import { useMemo } from "react";
import type { PlayTimeline } from "@/components/field/playback/timeline";
import { contrast } from "@/components/field/players/kit";
import { bannerAt, bannersFor, downText, formatClock, gameClockAt, playClockAt, scoreAt,
         type BannerTone } from "@/lib/broadcast";
import { formatSpot } from "@/lib/games";
import { breakAfter, driveEndingAt, statLowerThird, statsThrough, type DriveSummary,
         type TeamLine } from "@/lib/gameStats";
import type { GamePlayback, TeamSummary } from "@/lib/types";

const BANNER_STYLES: Record<BannerTone, string> = {
  gold: "bg-gold text-ink-950",
  red: "bg-rose-600 text-white",
  flag: "bg-yellow-400 text-ink-950",
  plain: "bg-ink-950/85 text-chalk ring-1 ring-white/15",
};

function quarterLabel(q: number): string {
  return q <= 4 ? `${["", "1st", "2nd", "3rd", "4th"][q]}` : q === 5 ? "OT" : `OT${q - 4}`;
}

/**
 * The broadcast graphics over the 3D view (docs/design/broadcast.md §3): a score bug along
 * the bottom with the running game clock, the play clock before the snap, the down and
 * distance; and banners at the moments that earn them. `time` is seconds into the play.
 */
export function BroadcastOverlay({ playback, index, timeline, time, replay = false }: {
  playback: GamePlayback;
  index: number; // the play in playback.plays
  timeline: PlayTimeline;
  time: number;
  /** During an instant replay: the bug holds the play's result (no banners, no play clock). */
  replay?: boolean;
}) {
  const play = playback.plays[index];
  const banners = useMemo(() => (play ? bannersFor(play, timeline) : []), [play, timeline]);
  const graphics = useMemo(() => {
    const roster = new Map(playback.players.map((p) => [p.id, p]));
    const plays = playback.plays;
    const shown = breakAfter(plays, index);
    return {
      lower: statLowerThird(plays, index, roster),
      drive: driveEndingAt(plays, index),
      break: shown,
      teams: shown ? statsThrough(plays, index).teams : null,
    };
  }, [index, playback]);
  if (!play) return null;
  const previous = playback.plays[index - 1];
  const { home, away } = playback.game;
  const score = replay ? play.score : scoreAt(play, previous, timeline, time);
  const clock = gameClockAt(play, timeline, replay ? timeline.duration : time);
  const playClock = replay ? null : playClockAt(play, time);
  const banner = replay ? null : bannerAt(banners, time);
  // After the whistle: the key player's stat line, how the drive went, the half or the game.
  const whistle = timeline.moments.find((m) => m.kind === "whistle")?.t ?? timeline.duration;
  const after = !replay && time >= whistle + 0.3;
  const [offense, defense] = play.side === "home" ? [home, away] : [away, home];
  const down = downText(play);
  const spot = play.ball_on != null && play.down != null
    ? formatSpot(play.ball_on, offense.abbreviation, defense.abbreviation) : null;

  return (
    <>
      {banner && (
        <div key={`${banner.t}-${banner.text}`} aria-live="polite" data-testid="banner"
          className={`pointer-events-none absolute left-1/2 top-[14%] -translate-x-1/2 animate-[banner_0.25s_ease-out] rounded-md px-5 py-1.5 font-display text-xl font-bold uppercase tracking-widest shadow-lg sm:text-2xl ${BANNER_STYLES[banner.tone]}`}>
          {banner.text}
        </div>
      )}
      {after && graphics.lower && (
        <div role="note" aria-label="Player stats" data-testid="lower-third"
          className="pointer-events-none absolute bottom-14 left-3 animate-[lower_0.3s_ease-out] overflow-hidden rounded-md shadow-lg ring-1 ring-black/40">
          <div className="bg-ink-950/90 px-3 py-1 font-display text-sm font-bold uppercase tracking-wide text-chalk">
            {graphics.lower.player && <span className="mr-1.5 text-gold">#{graphics.lower.player.number}</span>}
            {graphics.lower.player?.short_name ?? "Stand-in"}
            {graphics.lower.player && <span className="ml-1.5 text-xs text-mist">{graphics.lower.player.position}</span>}
          </div>
          <div className="bg-gold px-3 py-0.5 text-xs font-semibold text-ink-950">{graphics.lower.line}</div>
        </div>
      )}
      {after && graphics.drive && !graphics.break && (
        <DriveCard drive={graphics.drive} team={graphics.drive.side === "home" ? home : away} />
      )}
      {after && graphics.break && graphics.teams && (
        <BreakCard kind={graphics.break} home={home} away={away} score={play.score} teams={graphics.teams} />
      )}
      <div role="group" aria-label="Score bug"
        className="pointer-events-none absolute inset-x-2 bottom-2 flex items-stretch overflow-hidden whitespace-nowrap rounded-md text-sm shadow-lg ring-1 ring-black/40 sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2">
        <TeamCell team={away} score={score.away} timeouts={play.timeouts?.away} ball={play.side === "away"} />
        <TeamCell team={home} score={score.home} timeouts={play.timeouts?.home} ball={play.side === "home"} />
        <div className="flex items-center gap-2 bg-ink-950/90 px-3 font-display font-semibold tabular-nums">
          <span className="text-mist">{quarterLabel(play.quarter)}</span>
          <span data-testid="game-clock">{formatClock(clock)}</span>
        </div>
        {(down || spot) && (
          <div className="hidden items-center gap-1.5 bg-ink-900/90 px-3 font-display font-semibold sm:flex">
            <span className="text-gold" data-testid="down">{down}</span>
            {spot && <span className="text-xs text-mist">at {spot}</span>}
          </div>
        )}
        {playClock !== null && (
          <div className="flex items-center bg-ink-800/90 px-2 font-display text-xs font-semibold tabular-nums text-mist"
            aria-label={`Play clock ${playClock}`}>
            :{String(playClock).padStart(2, "0")}
          </div>
        )}
      </div>
    </>
  );
}

const INK = "#05070a"; // --color-ink-950

function TeamCell({ team, score, timeouts, ball }: {
  team: TeamSummary; score: number; timeouts: number | undefined; ball: boolean;
}) {
  // Dark text on light team colours, white on dark: whichever reads better.
  const light = contrast(team.primary_color, INK) > contrast(team.primary_color, "#ffffff");
  return (
    <div className="flex items-center gap-2 px-2.5 py-1" style={{ backgroundColor: team.primary_color }}
      data-testid={`bug-${team.abbreviation}`}>
      <span className={`font-display font-bold uppercase ${light ? "text-ink-950" : "text-white"}`}>
        {team.abbreviation}
      </span>
      <span className={`flex w-3 justify-center text-[10px] ${light ? "text-ink-950" : "text-white"}`}
        role={ball ? "img" : undefined} aria-label={ball ? "has the ball" : undefined}>
        {ball ? "●" : ""}
      </span>
      <div className="flex flex-col items-end">
        <span className={`stat-number text-lg ${light ? "text-ink-950" : "text-white"}`}>{score}</span>
        {timeouts != null && (
          <span className="flex gap-0.5" role="img" aria-label={`${timeouts} timeouts`}>
            {[0, 1, 2].map((i) => (
              <span key={i} className={`h-0.5 w-2 rounded ${i < timeouts ? (light ? "bg-ink-950" : "bg-white") : "bg-black/25"}`} />
            ))}
          </span>
        )}
      </div>
    </div>
  );
}

/** The instant replay's tag, with a wipe as it rolls, and a way out. */
export function ReplayBadge({ onSkip }: { onSkip: () => void }) {
  return (
    <>
      <div aria-hidden className="pointer-events-none absolute inset-0 animate-[wipe_0.5s_ease-in_forwards] bg-gradient-to-r from-transparent via-gold/60 to-transparent" />
      <div role="group" aria-label="Instant replay"
        className="absolute right-3 top-3 flex items-center gap-2 rounded-md bg-ink-950/85 py-1 pl-3 pr-1 shadow-lg ring-1 ring-gold/40">
        <span className="font-display text-sm font-bold uppercase tracking-[0.25em] text-gold">Replay</span>
        <button type="button" onClick={onSkip}
          className="rounded px-2 py-0.5 text-[11px] font-semibold text-mist hover:bg-white/10 hover:text-chalk">
          Skip replay
        </button>
      </div>
    </>
  );
}

function DriveCard({ drive, team }: { drive: DriveSummary; team: TeamSummary }) {
  return (
    <div role="note" aria-label="Drive summary" data-testid="drive-summary"
      className="pointer-events-none absolute bottom-14 right-3 animate-[lower_0.3s_ease-out] rounded-md bg-ink-950/90 px-3 py-1.5 text-xs shadow-lg ring-1 ring-white/10">
      <div className="font-display text-[11px] font-semibold uppercase tracking-widest text-mist">
        {team.abbreviation} drive
      </div>
      <div className="tabular-nums text-chalk">
        {drive.plays} plays · {drive.yards} yds · {formatClock(drive.seconds)} ·{" "}
        <span className="font-semibold text-gold">{drive.result}</span>
      </div>
    </div>
  );
}

const ROWS: [string, (t: TeamLine) => string][] = [
  ["Total yards", (t) => String(t.total_yds)],
  ["Passing", (t) => String(t.pass_yds)],
  ["Rushing", (t) => String(t.rush_yds)],
  ["First downs", (t) => String(t.first_downs)],
  ["3rd down", (t) => `${t.third_down_conv}/${t.third_down_att}`],
  ["Turnovers", (t) => String(t.turnovers)],
  ["Possession", (t) => formatClock(t.time_of_possession)],
];

function BreakCard({ kind, home, away, score, teams }: {
  kind: "halftime" | "final"; home: TeamSummary; away: TeamSummary; score: { home: number; away: number };
  teams: Record<"home" | "away", TeamLine>;
}) {
  return (
    <div role="note" aria-label={kind === "final" ? "Final stats" : "Halftime stats"} data-testid="break-card"
      className="pointer-events-none absolute left-1/2 top-1/2 w-72 -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg bg-ink-950/92 text-sm shadow-2xl ring-1 ring-white/10">
      <div className="bg-gold py-1 text-center font-display text-sm font-bold uppercase tracking-[0.2em] text-ink-950">
        {kind === "final" ? "Final" : "Halftime"}
      </div>
      <table className="w-full tabular-nums">
        <thead>
          <tr className="font-display text-xs uppercase">
            <th className="w-1/3 py-1.5" style={{ color: away.primary_color }}>{away.abbreviation} {score.away}</th>
            <th className="w-1/3" />
            <th className="w-1/3 py-1.5" style={{ color: home.primary_color }}>{home.abbreviation} {score.home}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([label, value]) => (
            <tr key={label} className="border-t border-white/5">
              <td className="py-1 text-center">{value(teams.away)}</td>
              <td className="py-1 text-center text-[11px] uppercase tracking-wider text-mist">{label}</td>
              <td className="py-1 text-center">{value(teams.home)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
