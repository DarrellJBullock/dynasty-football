"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { choreographGame } from "@/components/field/playback/choreograph";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { callLabel } from "@/lib/games";
import type { CoachSituation, CoachState, DefensivePlay, Game, GamePlayback, OffensivePlay,
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
export function CoachView({ game, playbook, initialState, initialPlayback }: {
  game: Game;
  playbook: Playbook;
  initialState: CoachState | null;
  initialPlayback: GamePlayback | null;
}) {
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

  async function run(request: () => Promise<CoachState>, showAll = true) {
    setBusy(true);
    setError(null);
    try {
      const next = await request();
      const plays = await api.playback(game.id);
      const total = plays.plays.length;
      const fresh = showAll ? next.new_plays : Math.min(next.new_plays, REEL_LENGTH);
      setState(next);
      setPlayback(plays);
      setReel((r) => ({ key: r.key + 1, from: Math.max(0, total - Math.max(fresh, 1)) }));
      setTab(suggestedTab(next.situation, playbook));
      setPkg("auto");
      setTimeoutCall(false);
      setConfirmFinish(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!state) return <StartScreen game={game} busy={busy} error={error}
    onStart={() => run(() => api.startCoaching(game.id))} />;

  const { situation } = state;
  const mine = state.side;
  const theirs = mine === "home" ? "away" : "home";
  const teams = { home: game.home, away: game.away };

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href="/" className="text-sm text-gold hover:underline">← Dashboard</Link>
        <span className="eyebrow">
          Coach Mode · {game.away.full_name} at {game.home.full_name} · {game.round_name ?? `Week ${game.week}`}
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
                <h2 className="font-display text-xl font-bold uppercase">
                  {situation.role === "offense" ? "Your offense" : "Your defense"}
                </h2>
                <p className="text-sm text-mist" data-testid="situation">
                  {situation.offense} {ordinal(situation.down)} &amp;{" "}
                  {situation.ball_on + situation.distance >= 100 ? "Goal" : situation.distance} at{" "}
                  {situation.spot}
                </p>
              </header>

              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-gold/[0.06] px-3 py-2 text-sm">
                <span className="text-mist">AI suggests</span>
                <span className="font-semibold">{situation.suggestion_name}</span>
                {situation.suggested_package && <span className="text-xs text-mist">({situation.suggested_package})</span>}
                <button type="button" className="btn btn-primary ml-auto px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => api.coachCall(game.id, {
                    play: situation.suggestion, package: situation.suggested_package, timeout }))}>
                  Call it
                </button>
              </div>

              <PlaybookGrid role={situation.role} playbook={playbook} tab={tab} setTab={setTab}
                suggestion={situation.suggestion} busy={busy}
                onCall={(play) => run(() => api.coachCall(game.id, {
                  play, timeout, package: situation.role === "defense" && pkg !== "auto" ? pkg : null }))} />

              <div className="flex flex-wrap items-center gap-4 border-t border-white/5 pt-3 text-sm">
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
              </div>

              <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3" role="group"
                aria-label="Let the AI call">
                <span className="text-xs text-mist">Let the AI call</span>
                <button type="button" className="btn btn-ghost px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => api.coachAuto(game.id, "play"))}>This play</button>
                <button type="button" className="btn btn-ghost px-3 py-1 text-xs" disabled={busy}
                  onClick={() => run(() => api.coachAuto(game.id, "drive"), false)}>This drive</button>
                {confirmFinish ? (
                  <>
                    <button type="button" className="btn btn-primary px-3 py-1 text-xs" disabled={busy}
                      onClick={() => run(() => api.coachAuto(game.id, "game"), false)}>
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

function ScoreBug({ state, teams }: { state: CoachState; teams: { home: Game["home"]; away: Game["away"] } }) {
  const s = state.situation;
  const score = s?.score ?? { home: state.game.home_score ?? 0, away: state.game.away_score ?? 0 };
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
        ) : (
          <div className="font-display text-lg font-semibold uppercase">
            {state.game.overtime ? "Final / OT" : "Final"}
          </div>
        )}
      </div>
    </section>
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

function DriveLog({ state }: { state: CoachState }) {
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

function FinalCard({ state, teams, mine, theirs }: {
  state: CoachState; teams: { home: Game["home"]; away: Game["away"] }; mine: "home" | "away";
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
