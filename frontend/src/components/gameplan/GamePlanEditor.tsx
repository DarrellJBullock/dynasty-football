"use client";

import { useState } from "react";
import { PageHeader, Panel } from "@/components/ui/Panel";
import { api } from "@/lib/api";
import type { GamePlan, Playbook, TeamSummary } from "@/lib/types";

const LEVELS: [number, string][] = [[-2, "Much less"], [-1, "Less"], [0, "Usual"], [1, "More"], [2, "Much more"]];
const LEVEL_NAME = Object.fromEntries(LEVELS);

const OFFENSE_GROUPS: [string, string][] = [
  ["run", "Runs"], ["quick", "Quick passes"], ["intermediate", "Intermediate passes"],
  ["deep", "Deep passes"], ["play_action", "Play action"], ["screen", "Screens"],
];
const DEFENSE_GROUPS: [string, string][] = [
  ["zone", "Zone coverage"], ["man", "Man coverage"], ["pressure", "Pressure"], ["situational", "Situational"],
];

/**
 * The franchise's game plan: the plays and calls the AI makes for it (when it sims, when
 * Coach Mode lets the AI call, when simming ahead) and its tendencies. A plan must keep a
 * play for every kind of situation; the page says what's missing before saving.
 */
export function GamePlanEditor({ initial, playbook, team }: {
  initial: GamePlan; playbook: Playbook; team: TeamSummary;
}) {
  const [saved, setSaved] = useState(initial);
  const [offense, setOffense] = useState(new Set(initial.offense));
  const [defense, setDefense] = useState(new Set(initial.defense));
  const [tendencies, setTendencies] = useState(initial.tendencies);
  const [offenseAudibles, setOffenseAudibles] = useState(initial.offense_audibles);
  const [defenseAudibles, setDefenseAudibles] = useState(initial.defense_audibles);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const missing = saved.required
    .filter((r) => !r.keys.some((k) => (r.side === "offense" ? offense : defense).has(k)))
    .map((r) => r.label);

  function load(plan: GamePlan) {
    setSaved(plan);
    setOffense(new Set(plan.offense));
    setDefense(new Set(plan.defense));
    setTendencies(plan.tendencies);
    setOffenseAudibles(plan.offense_audibles);
    setDefenseAudibles(plan.defense_audibles);
  }

  async function act(run: () => Promise<GamePlan>, done: string) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      load(await run());
      setStatus(done);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // (an audible must be in the plan: one switched off drops out)
  const keep = (audibles: string[], chosen: Set<string>) =>
    [...new Set(audibles)].filter((key) => chosen.has(key));
  const save = () => act(() => api.saveGamePlan(team.id, {
    offense: [...offense].sort(), defense: [...defense].sort(), tendencies,
    offense_audibles: keep(offenseAudibles, offense), defense_audibles: keep(defenseAudibles, defense),
  }), "Game plan saved.");
  const reset = () => act(() => api.resetGamePlan(team.id), "Back to the plan for your roster.");

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader eyebrow={team.full_name} title="Game plan">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-mist">
            {saved.custom ? "Your plan" : "Suggested for your roster"}
          </span>
          {saved.custom && (
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={reset}>
              Reset to the suggested plan
            </button>
          )}
          <button type="button" className="btn btn-primary" disabled={busy || missing.length > 0}
            onClick={save}>
            {busy ? "Saving…" : "Save game plan"}
          </button>
        </div>
      </PageHeader>
      <p className="mb-4 max-w-3xl text-sm text-mist">
        The AI calls plays from this plan whenever it calls for your team: simmed games, Coach
        Mode&apos;s &ldquo;let the AI call&rdquo;, and simming ahead. Your own calls in Coach Mode can use the whole book.
      </p>
      {missing.length > 0 && (
        <p role="alert" className="mb-4 text-sm text-rose-300">
          The plan needs {missing.join(", ")}.
        </p>
      )}
      {status && <p role="status" className="mb-4 text-sm text-emerald-300">{status}</p>}
      {error && <p role="alert" className="mb-4 text-sm text-rose-300">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Panel title="Offense">
            <PlayGroups groups={OFFENSE_GROUPS} chosen={offense} setChosen={setOffense}
              plays={playbook.offense.filter((p) => saved.offense_choices.includes(p.key))} />
          </Panel>
          <Panel title="Defense">
            <PlayGroups groups={DEFENSE_GROUPS} chosen={defense} setChosen={setDefense}
              plays={playbook.defense.filter((p) => saved.defense_choices.includes(p.key))} />
          </Panel>
        </div>
        <div className="space-y-6 self-start">
        <Panel title="Tendencies">
          <div className="space-y-4">
            {Object.entries(saved.tendency_labels).map(([key, label]) => (
              <fieldset key={key}>
                <legend className="text-sm font-medium">{label}</legend>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {LEVELS.map(([level, name]) => (
                    <label key={level} className={`cursor-pointer rounded-md border px-2 py-1 text-xs ${
                      (tendencies[key] ?? 0) === level ? "border-gold/60 bg-gold/10 text-chalk" : "border-white/10 text-mist hover:border-white/20"}`}>
                      <input type="radio" name={key} value={level} className="sr-only"
                        checked={(tendencies[key] ?? 0) === level}
                        onChange={() => setTendencies({ ...tendencies, [key]: level })} />
                      {name}
                    </label>
                  ))}
                </div>
                {(saved.suggested[key] ?? 0) !== 0 && (
                  <p className="mt-1 text-xs text-mist">
                    Suggested for your roster: {LEVEL_NAME[saved.suggested[key]]}
                  </p>
                )}
              </fieldset>
            ))}
          </div>
        </Panel>
        <Panel title="Audibles">
          <p className="mb-3 text-xs text-mist">
            In Coach Mode, after you call a play you see the other side&apos;s look and can
            switch to one of these. None: plays snap as called.
          </p>
          <AudiblePicks side="Offensive" chosen={offenseAudibles} setChosen={setOffenseAudibles}
            plays={playbook.offense.filter((p) => offense.has(p.key))} />
          <AudiblePicks side="Defensive" chosen={defenseAudibles} setChosen={setDefenseAudibles}
            plays={playbook.defense.filter((p) => defense.has(p.key))} />
        </Panel>
        </div>
      </div>
    </div>
  );
}

/** Up to three audibles for one side, from the plays in the plan. */
function AudiblePicks({ side, plays, chosen, setChosen }: {
  side: string; plays: { key: string; name: string }[]; chosen: string[];
  setChosen: (next: string[]) => void;
}) {
  return (
    <fieldset className="mb-3 space-y-1.5">
      <legend className="text-sm font-medium">{side} audibles</legend>
      {[0, 1, 2].map((i) => (
        <select key={i} className="field-input py-1 text-sm" aria-label={`${side} audible ${i + 1}`}
          value={chosen[i] ?? ""}
          onChange={(e) => {
            const next = [...chosen];
            next[i] = e.target.value;
            setChosen(next.filter(Boolean));
          }}>
          <option value="">—</option>
          {plays.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
        </select>
      ))}
    </fieldset>
  );
}

function PlayGroups<P extends { key: string; name: string; category: string; description: string }>({
  groups, plays, chosen, setChosen,
}: {
  groups: [string, string][]; plays: P[]; chosen: Set<string>; setChosen: (next: Set<string>) => void;
}) {
  function toggle(key: string) {
    const next = new Set(chosen);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setChosen(next);
  }
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {groups.map(([category, title]) => {
        const inGroup = plays.filter((p) => p.category === category);
        if (!inGroup.length) return null;
        return (
          <fieldset key={category}>
            <legend className="eyebrow mb-2">{title}</legend>
            <ul className="space-y-2">
              {inGroup.map((play) => (
                <li key={play.key}>
                  <label className="flex cursor-pointer items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-1 accent-[var(--color-gold)]"
                      checked={chosen.has(play.key)} onChange={() => toggle(play.key)} />
                    <span>
                      <span className="font-medium">{play.name}</span>
                      <span className="block text-xs text-mist">{play.description}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        );
      })}
    </div>
  );
}
