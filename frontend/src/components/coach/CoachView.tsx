"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { choreographGame } from "@/components/field/playback/choreograph";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { callLabel } from "@/lib/games";
import type { CoachCallIn, CoachSituation, CoachState, DefensivePlay, FatigueLine, Game, GamePlayback, OffensivePlay,
              Playbook } from "@/lib/types";
import { PlayReel } from "./PlayReel";

type Package = "base" | "nickel" | "dime";

const OFFENSE_TABS: { key: OffensivePlay["category"]; label: string }[] = [
  { key: "run", label: "Run" }, { key: "quick", label: "Quick" },
  { key: "intermediate", label: "Intermediate" }, { key: "deep", label: "Deep" },
  { key: "play_action", label: "Play action" }, { key: "screen", label: "Screen" },
  { key: "special", label: "Special" },
];
const DEFENSE_TABS: { key: DefensivePlay["category"]; label: string }[] = [
  { key: "zone", label: "Zone" }, { key: "man", label: "Man" }, { key: "pressure", label: "Pressure" },
  { key: "situational", label: "Situational" },
];
const PACKAGES: Package[] = ["base", "nickel", "dime"];
const HEADINGS: Record<CoachSituation["role"], string> = {
  offense: "Your offense", defense: "Your defense", kickoff: "Your kickoff", conversion: "After the touchdown",
  audible: "At the line",
};
const KICK_CHOICES: Record<"kickoff" | "conversion", { key: string; label: string; note: string }[]> = {
  kickoff: [
    { key: "normal", label: "Kick it deep", note: "Usually a touchback; otherwise they return it." },
    { key: "squib", label: "Squib kick", note: "Low and bouncing: no touchback, but no long return either." },
    { key: "onside", label: "Onside kick", note: "Try to get it back (about one in eight); a short field if it fails." },
  ],
  conversion: [
    { key: "kick", label: "Extra point", note: "Almost automatic: one point." },
    { key: "two", label: "Go for two", note: "One play from the 2, about half the time: two points." },
  ],
};
/** What the screen needs from a coached game: Coach Mode's state, or a live game's (LiveView). */
export type CoachViewState = Pick<CoachState, "game" | "team" | "side" | "situation" | "plays" | "new_plays"> & {
  status: string;
  /** A live game: the other coach the snap waits on (abbreviations). */
  waiting_on?: string[];
  /** A live game's call clock: when the AI calls for whoever hasn't. */
  deadline?: string | null;
};

/** How calls reach the game: Coach Mode's API by default; a live game passes its own. */
export interface CoachActions {
  call: (call: CoachCallIn) => Promise<CoachViewState>;
  auto: (scope: "play" | "drive" | "game") => Promise<CoachViewState>;
  /** Reload the game (a live game polls it while it waits on the other coach). */
  load?: () => Promise<CoachViewState>;
}

export const POLL_MS = 4000;
const REEL_LENGTH = 4; // after letting the AI call a stretch, show only its last few plays

function ordinal(n: number): string {
  return ["", "1st", "2nd", "3rd", "4th"][n] ?? `${n}th`;
}

function quarterLabel(q: number): string {
  return q <= 4 ? `Q${q}` : q === 5 ? "OT" : `OT${q - 4}`;
}

/** The playbook tab the AI's suggestion is on, so it's on screen. */
function suggestedTab(situation: CoachSituation | null, playbook: Playbook): string {
  if (!situation) return "run";
  const plays = situation.role === "offense" ? playbook.offense : playbook.defense;
  return plays.find((p) => p.key === situation.suggestion)?.category
    ?? (situation.role === "offense" ? "run" : "zone");
}

/**
 * Coach Mode: call every snap of your team's game from the playbook, watch it run in 3D,
 * and live with the result.
 */
export function CoachView({ game, playbook, initialState, initialPlayback, actions, mode = "Coach Mode" }: {
  game: Game;
  playbook: Playbook;
  initialState: CoachViewState | null;
  initialPlayback: GamePlayback | null;
  actions?: CoachActions;
  mode?: string;
}) {
  const act: CoachActions = actions ?? {
    call: (c) => api.coachCall(game.id, c),
    auto: (scope) => api.coachAuto(game.id, scope),
  };
  const [state, setState] = useState(initialState);
  const [playback, setPlayback] = useState(initialPlayback);
  const [reel, setReel] = useState({ key: 0, from: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(() => suggestedTab(initialState?.situation ?? null, playbook));
  const [pkg, setPkg] = useState<Package | "auto">("auto");
  const [timeout, setTimeoutCall] = useState(false);
  const [show3d, setShow3d] = useState(true);
  const [confirmFinish, setConfirmFinish] = useState(false);

  const choreographed = useMemo(() => (playback ? choreographGame(playback) : []), [playback]);
  const reelPlays = choreographed.slice(reel.from);

  async function show(next: CoachViewState, fresh: number) {
    const plays = await api.playback(game.id);
    const total = plays.plays.length;
    setState(next);
    setPlayback(plays);
    setReel((r) => ({ key: r.key + 1, from: Math.max(0, total - Math.max(fresh, 1)) }));
    setTab(suggestedTab(next.situation, playbook));
    setPkg("auto");
    setTimeoutCall(false);
    setConfirmFinish(false);
  }

  async function run(request: () => Promise<CoachViewState>, showAll = true) {
    setBusy(true);
    setError(null);
    try {
      const next = await request();
      await show(next, showAll ? next.new_plays : Math.min(next.new_plays, REEL_LENGTH));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // A live game waiting on the other coach: poll until the snap plays (or it's our call).
  const waiting = state?.status === "in_progress" && !state.situation;
  const latest = useRef(state);
  useEffect(() => { latest.current = state; }, [state]);
  const load = actions?.load;
  useEffect(() => {
    if (!waiting || !load) return;
    const timer = setInterval(async () => {
      try {
        const next = await load();
        const now = latest.current;
        if (!now) return;
        const fresh = next.plays.length - now.plays.length;
        if (fresh > 0 || next.status !== now.status || Boolean(next.situation) !== Boolean(now.situation)) {
          await show(next, Math.min(Math.max(fresh, 0), REEL_LENGTH));
        }
      } catch {
        // (try again next time)
      }
    }, POLL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, load]);

  if (!state) return <StartScreen game={game} busy={busy} error={error}
    onStart={() => run(() => api.startCoaching(game.id))} />;

  const { situation } = state;
  const kicking = situation?.role === "kickoff" || situation?.role === "conversion";
  const mine = state.side;
  const theirs = mine === "home" ? "away" : "home";
  const teams = { home: game.home, away: game.away };

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href="/" className="text-sm text-gold hover:underline">← Dashboard</Link>
        <span className="eyebrow">
          {mode} · {game.away.full_name} at {game.home.full_name} · {game.round_name ?? `Week ${game.week}`}
        </span>
      </div>

      <ScoreBug state={state} teams={teams} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          {show3d && playback && reelPlays.length > 0 && (
            <PlayReel key={reel.key} playback={playback} reel={reelPlays} />
          )}

          {situation ? (
            <section className="panel space-y-4 p-4" aria-label="Your call">
              <header className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="font-display text-xl font-bold uppercase">{HEADINGS[situation.role]}</h2>
                {kicking ? (
                  <p className="text-sm text-mist" data-testid="situation">
                    {situation.role === "conversion" ? "Touchdown! " : ""}
                    {quarterLabel(situation.quarter)} {situation.clock} · score{" "}
                    {situation.score[mine]}–{situation.score[theirs]}
                  </p>
                ) : (
                  <p className="text-sm text-mist" data-testid="situation">
                    {situation.offense} {ordinal(situation.down)} &amp;{" "}
                    {situation.ball_on + situation.distance >= 100 ? "Goal" : situation.distance} at{" "}
                    {situation.spot}
                  </p>
                )}
              </header>

              {situation.role === "audible" ? (
                <AtTheLine situation={situation} busy={busy}
                  onCall={(play) => run(() => act.call({ play }))} />
              ) : (<>
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-gold/[0.06] px-3 py-2 text-sm">
                <span className="text-mist">AI suggests</span>
                <span className="font-semibold">{situation.suggestion_name}</span>
                {situation.suggested_package && <span className="text-xs text-mist">({situation.suggested_package})</span>}
                <button type="button" className="btn btn-primary ml-auto px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => act.call({
                    play: situation.suggestion, package: situation.suggested_package, timeout }))}>
                  Call it
                </button>
              </div>

              {situation.role === "kickoff" || situation.role === "conversion" ? (
                <KickChoices role={situation.role} suggestion={situation.suggestion} busy={busy}
                  onCall={(play) => run(() => act.call({ play }))} />
              ) : (
                <PlaybookGrid role={situation.role} playbook={playbook} tab={tab} setTab={setTab}
                  suggestion={situation.suggestion} busy={busy}
                  onCall={(play) => run(() => act.call({
                    play, timeout, package: situation.role === "defense" && pkg !== "auto" ? pkg : null }))} />
              )}

              {!kicking && <div className="flex flex-wrap items-center gap-4 border-t border-white/5 pt-3 text-sm">
                {situation.role === "defense" && (
                  <div role="radiogroup" aria-label="Personnel" className="flex items-center gap-1">
                    <span className="mr-1 text-xs text-mist">Personnel</span>
                    {(["auto", ...PACKAGES] as const).map((p) => (
                      <button key={p} type="button" role="radio" aria-checked={pkg === p}
                        className={`rounded-md px-2 py-1 text-xs font-semibold capitalize ${
                          pkg === p ? "bg-white/10 text-chalk" : "text-mist hover:text-chalk"}`}
                        onClick={() => setPkg(p)}>
                        {p === "auto" ? `Auto (${situation.suggested_package ?? "base"})` : p}
                      </button>
                    ))}
                  </div>
                )}
                <label className={`flex items-center gap-2 text-xs ${
                  situation.clock_running && situation.timeouts[mine] > 0 ? "text-chalk" : "text-mist/60"}`}>
                  <input type="checkbox" checked={timeout} onChange={(e) => setTimeoutCall(e.target.checked)}
                    disabled={!situation.clock_running || situation.timeouts[mine] <= 0} />
                  Call a timeout first ({situation.timeouts[mine]} left)
                  {!situation.clock_running && <span className="text-mist/60">· clock stopped</span>}
                </label>
              </div>}
              {!kicking && <Fatigue lines={situation.fatigue ?? []} mine={state.team.abbreviation} />}
              </>)}

              <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3" role="group"
                aria-label="Let the AI call">
                <span className="text-xs text-mist">Let the AI call</span>
                <button type="button" className="btn btn-ghost px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => act.auto("play"))}>This play</button>
                <button type="button" className="btn btn-ghost px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => act.auto("drive"), false)}>This drive</button>
                {confirmFinish ? (
                  <>
                    <button type="button" className="btn btn-primary px-3 py-1 text-xs" disabled={busy}
                      onClick={() => run(() => act.auto("game"), false)}>
                      Confirm: the AI finishes the game
                    </button>
                    <button type="button" className="btn btn-ghost px-3 py-1 text-xs"
                      onClick={() => setConfirmFinish(false)}>Cancel</button>
                  </>
                ) : (
                  <button type="button" className="btn btn-ghost px-3 py-1 text-xs" disabled={busy}
                    onClick={() => setConfirmFinish(true)}>The rest of the game</button>
                )}
                <label className="ml-auto flex items-center gap-2 text-xs text-mist">
                  <input type="checkbox" checked={show3d} onChange={(e) => setShow3d(e.target.checked)} />
                  Show plays in 3D
                </label>
              </div>
              {busy && <p className="text-xs text-mist" aria-live="polite">Running the play…</p>}
              {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
            </section>
          ) : waiting ? (
            <WaitingCard state={state} />
          ) : (
            <FinalCard state={state} teams={teams} mine={mine} theirs={theirs} />
          )}
        </div>

        <DriveLog state={state} />
      </div>
    </div>
  );
}

function StartScreen({ game, busy, error, onStart }: {
  game: Game; busy: boolean; error: string | null; onStart: () => void;
}) {
  return (
    <div className="mx-auto max-w-3xl">
      <section className="panel space-y-5 p-6 text-center" aria-label="Coach this game">
        <p className="eyebrow">{game.round_name ?? `Week ${game.week}`} · Coach Mode</p>
        <div className="flex items-center justify-center gap-6">
          <TeamCrest team={game.away} size={56} />
          <span className="font-display text-lg text-mist">at</span>
          <TeamCrest team={game.home} size={56} />
        </div>
        <h1 className="font-display text-2xl font-bold uppercase">
          {game.away.full_name} at {game.home.full_name}
        </h1>
        {game.status === "final" ? (
          <p className="text-sm text-mist">
            This game has been played. <Link href={`/games/${game.id}`} className="text-gold hover:underline">Box score</Link>
          </p>
        ) : (
          <>
            <p className="text-sm text-mist">
              Call every play from your playbook, on offense and defense, and watch each one in
              3D. The AI suggests a call every snap, and you can hand it a play, a drive, or the
              rest of the game at any time. Your rosters are locked in as they are now.
            </p>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={onStart}>
              {busy ? "Kicking off…" : "Start coaching"}
            </button>
          </>
        )}
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      </section>
    </div>
  );
}

function ScoreBug({ state, teams }: { state: CoachViewState; teams: { home: Game["home"]; away: Game["away"] } }) {
  const s = state.situation;
  const last = state.plays.at(-1);
  const score = s?.score ?? (state.status === "in_progress" && last
    ? { home: last.home_score, away: last.away_score }
    : { home: state.game.home_score ?? 0, away: state.game.away_score ?? 0 });
  return (
    <section className="panel flex flex-wrap items-center justify-between gap-4 px-5 py-3" aria-label="Scoreboard">
      {(["away", "home"] as const).map((side) => (
        <div key={side} className={`flex items-center gap-3 ${side === "home" ? "flex-row-reverse text-right" : ""}`}>
          <TeamCrest team={teams[side]} size={36} />
          <div>
            <div className="flex items-center gap-1.5 font-display text-sm font-semibold uppercase">
              {teams[side].abbreviation}
              {state.side === side && <span className="rounded bg-gold/15 px-1 text-[10px] text-gold">You</span>}
              {s?.possession === side && <span className="text-gold" title="Possession" aria-label="Possession">●</span>}
            </div>
            {s && (
              <div className="flex gap-0.5" aria-label={`${teams[side].abbreviation} timeouts: ${s.timeouts[side]}`}>
                {[0, 1, 2].map((i) => (
                  <span key={i} className={`h-1 w-3 rounded ${i < s.timeouts[side] ? "bg-gold" : "bg-white/10"}`} />
                ))}
              </div>
            )}
          </div>
          <span className="stat-number text-3xl" data-testid={`coach-score-${side}`}>{score[side]}</span>
        </div>
      ))}
      <div className="order-first w-full text-center text-sm sm:order-none sm:w-auto">
        {s ? (
          <>
            <div className="font-display text-lg font-semibold tabular-nums">
              {quarterLabel(s.quarter)} {s.clock}
            </div>
            <div className="text-xs text-mist">{s.clock_running ? "Clock running" : "Clock stopped"}</div>
          </>
        ) : state.status === "in_progress" ? (
          <>
            <div className="font-display text-lg font-semibold uppercase">
              {last ? `${quarterLabel(last.quarter)} ${last.clock}` : "Kickoff"}
            </div>
            <div className="text-xs text-mist">Live</div>
          </>
        ) : (
          <div className="font-display text-lg font-semibold uppercase">
            {state.game.overtime ? "Final / OT" : "Final"}
          </div>
        )}
      </div>
    </section>
  );
}

/** What the other side shows, in words. */
/** Each side's most tired players: energy bars, and who is resting on the sideline. */
export function Fatigue({ lines, mine }: { lines: FatigueLine[]; mine: string }) {
  const sides = [
    { label: "Your tired players", rows: lines.filter((l) => l.team === mine) },
    { label: "Their tired players", rows: lines.filter((l) => l.team !== mine) },
  ];
  return (
    <section aria-label="Fatigue" className="grid gap-3 border-t border-white/5 pt-3 sm:grid-cols-2">
      {sides.map(({ label, rows }) => (
        <div key={label}>
          <h3 className="mb-1 text-xs text-mist">{label}</h3>
          {rows.length === 0 ? <p className="text-xs text-mist/70">Everyone is fresh.</p> : (
            <ul className="space-y-1">
              {rows.map((l) => (
                <li key={l.player_id} className="flex items-center gap-2 text-xs">
                  <span className="w-8 shrink-0 text-mist">{l.position}</span>
                  <span className="min-w-0 flex-1 truncate">{l.name}</span>
                  {l.resting && <span className="text-[10px] uppercase text-amber-300">Resting</span>}
                  <div role="meter" aria-label={`${l.name} energy`} aria-valuemin={0} aria-valuemax={100}
                    aria-valuenow={l.energy} className="h-1.5 w-16 shrink-0 overflow-hidden rounded bg-white/10">
                    <div className={`h-full ${l.energy < 70 ? "bg-rose-400" : l.energy < 85 ? "bg-amber-300" : "bg-emerald-400"}`}
                      style={{ width: `${l.energy}%` }} />
                  </div>
                  <span className="w-6 text-right tabular-nums text-mist">{l.energy}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}

export function lookText(situation: CoachSituation): string {
  const look = situation.look ?? {};
  if (situation.audible_for === "defense") {
    return `The offense lines up in ${look.formation ?? "its formation"}.`;
  }
  const safeties = { two_high: "two deep safeties", single_high: "one deep safety", none: "no deep safety" };
  return `The defense shows ${look.package ?? "base"} personnel, ` +
    `${safeties[look.safeties ?? "single_high"]}${look.blitz ? ", and a blitz" : ", no blitz"}.`;
}

/** At the line (audibles in the game plan): keep the call, or switch to an audible. */
function AtTheLine({ situation, busy, onCall }: {
  situation: CoachSituation; busy: boolean; onCall: (play: string) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm">
        You called <span className="font-semibold">{situation.called?.name}</span>.{" "}
        <span data-testid="look">{lookText(situation)}</span>
        {situation.audible_for === "offense" && (
          <span className="text-mist"> (Defenses sometimes disguise what they&apos;re in.)</span>
        )}
      </p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Audibles">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onCall("keep")}>
          Keep: {situation.called?.name}
        </button>
        {(situation.audibles ?? []).filter((a) => a.key !== situation.called?.key).map((a) => (
          <button key={a.key} type="button" className="btn btn-ghost" disabled={busy}
            onClick={() => onCall(a.key)}>
            Audible: {a.name}
          </button>
        ))}
      </div>
    </div>
  );
}

function KickChoices({ role, suggestion, busy, onCall }: {
  role: "kickoff" | "conversion"; suggestion: string; busy: boolean; onCall: (choice: string) => void;
}) {
  return (
    <ul className="grid gap-2 sm:grid-cols-3" aria-label={role === "kickoff" ? "Kickoff" : "Conversion"}>
      {KICK_CHOICES[role].map((c) => (
        <li key={c.key}>
          <button type="button" disabled={busy}
            aria-label={`${c.label}${c.key === suggestion ? " (AI pick)" : ""}`}
            className={`h-full w-full rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-50 ${
              c.key === suggestion ? "border-gold/50 bg-gold/[0.07]" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]"}`}
            onClick={() => onCall(c.key)}>
            <span className="flex items-center justify-between gap-2">
              <span className="font-semibold">{c.label}</span>
              {c.key === suggestion && <span className="text-[10px] font-semibold uppercase text-gold">AI pick</span>}
            </span>
            <span className="mt-1 block text-xs leading-snug text-mist/80">{c.note}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function PlaybookGrid({ role, playbook, tab, setTab, suggestion, busy, onCall }: {
  role: "offense" | "defense";
  playbook: Playbook;
  tab: string;
  setTab: (tab: string) => void;
  suggestion: string;
  busy: boolean;
  onCall: (play: string) => void;
}) {
  const tabs = role === "offense" ? OFFENSE_TABS : DEFENSE_TABS;
  const plays: (OffensivePlay | DefensivePlay)[] = (role === "offense" ? playbook.offense : playbook.defense)
    .filter((p) => p.category === tab);
  return (
    <div className="space-y-3">
      <div role="tablist" aria-label={role === "offense" ? "Offensive plays" : "Defensive calls"}
        className="flex flex-wrap gap-1">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
            className={`rounded-md px-2.5 py-1 text-xs font-semibold ${
              tab === t.key ? "bg-gold text-ink-950" : "bg-white/[0.04] text-mist hover:text-chalk"}`}
            onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" aria-label="Plays">
        {plays.map((p) => (
          <li key={p.key}>
            <button type="button" disabled={busy} title={p.description}
              aria-label={`${p.name}${p.key === suggestion ? " (AI pick)" : ""}`}
              className={`h-full w-full rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-50 ${
                p.key === suggestion ? "border-gold/50 bg-gold/[0.07]" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]"}`}
              onClick={() => onCall(p.key)}>
              <span className="flex items-center justify-between gap-2">
                <span className="font-semibold">{p.name}</span>
                {p.key === suggestion && <span className="text-[10px] font-semibold uppercase text-gold">AI pick</span>}
              </span>
              <span className="block text-xs text-mist">
                {"formation" in p ? p.formation : p.coverage === "man" ? "Man" : "Zone"}
                {"blitz" in p && p.blitz ? " · blitz" : ""}
              </span>
              <span className="mt-1 block text-xs leading-snug text-mist/80">{p.description}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DriveLog({ state }: { state: CoachViewState }) {
  const recent = [...state.plays].reverse().slice(0, 12);
  return (
    <aside className="panel self-start p-0" aria-label="Play-by-play">
      <h2 className="eyebrow px-4 pb-2 pt-4">Play-by-play</h2>
      <ol className="divide-y divide-white/[0.04]">
        {recent.map((play) => (
          <li key={play.n} className="px-4 py-2 text-xs">
            <div className="flex justify-between text-mist">
              <span className="tabular-nums">{quarterLabel(play.quarter)} {play.clock}</span>
              <span>{play.down ? `${play.offense} ${ordinal(play.down)}&${play.distance}` : play.offense}</span>
            </div>
            <p className="mt-0.5 text-chalk">{play.text}</p>
            {callLabel(play.play_name, play.defense_name) && (
              <p className="text-mist">{callLabel(play.play_name, play.defense_name)}</p>
            )}
          </li>
        ))}
      </ol>
    </aside>
  );
}

/** A live game: our call is in (or it's theirs), and the snap waits on the other coach. */
function WaitingCard({ state }: { state: CoachViewState }) {
  const who = state.waiting_on?.length ? state.waiting_on.join(" and ") : "the other coach";
  return (
    <section className="panel space-y-2 p-6 text-center" aria-label="Waiting">
      <h2 className="font-display text-xl font-bold uppercase">Waiting on {who}</h2>
      <p className="text-sm text-mist" aria-live="polite">
        The snap plays as soon as {who} calls; this page updates by itself.
        {state.deadline && <> If there&apos;s no call by {new Date(state.deadline).toLocaleString()}, the
          AI calls it from their game plan.</>}
      </p>
    </section>
  );
}

function FinalCard({ state, teams, mine, theirs }: {
  state: CoachViewState; teams: { home: Game["home"]; away: Game["away"] }; mine: "home" | "away";
  theirs: "home" | "away";
}) {
  const { game } = state;
  const us = (mine === "home" ? game.home_score : game.away_score) ?? 0;
  const them = (theirs === "home" ? game.home_score : game.away_score) ?? 0;
  const verdict = us > them ? "You won" : us < them ? "You lost" : "A tie";
  return (
    <section className="panel space-y-3 p-6 text-center" aria-label="Final">
      <p className="eyebrow">Final{game.overtime ? " / OT" : ""}</p>
      <h2 className="font-display text-3xl font-bold uppercase">{verdict}, {us}–{them}</h2>
      <p className="text-sm text-mist">
        {teams[mine].full_name} vs {teams[theirs].full_name}. The result counts in the standings,
        stats and records like any other game; simulate the rest of the week from the Dashboard.
      </p>
      <div className="flex flex-wrap justify-center gap-3 text-sm">
        <Link href={`/games/${game.id}`} className="btn btn-primary">Box score</Link>
        <Link href={`/games/${game.id}/watch`} className="btn btn-ghost">Watch the game</Link>
        <Link href="/" className="btn btn-ghost">Dashboard</Link>
      </div>
    </section>
  );
}
