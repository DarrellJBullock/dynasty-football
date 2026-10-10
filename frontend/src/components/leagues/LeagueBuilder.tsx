"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import { formatMoney } from "@/lib/format";
import {
  DEFAULT_STRUCTURE,
  duplicateAbbreviations,
  renameConference,
  renameDivision,
  specProblems,
  structureError,
  totalTeams,
  updateTeam,
  type Structure,
  type TeamPath,
} from "@/lib/leagueBuilder";
import type { LeagueCreate, TeamIdentity } from "@/lib/types";

const RANGE = (n: number) => Array.from({ length: n }, (_, i) => i + 1);

export function LeagueBuilder() {
  const router = useRouter();
  const [structure, setStructure] = useState<Structure>(DEFAULT_STRUCTURE);
  const [spec, setSpec] = useState<LeagueCreate | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidStructure = structureError(structure);

  useEffect(() => {
    if (invalidStructure) return;
    let cancelled = false;
    api
      .leagueTemplate(structure.conferences, structure.divisions, structure.teamsPerDivision)
      .then((template) => {
        if (cancelled) return;
        // Keep league-level settings the user already typed; teams come from the template.
        setSpec((current) =>
          current
            ? { ...template, name: current.name, abbreviation: current.abbreviation,
                salary_cap: current.salary_cap, season_year: current.season_year,
                weeks: current.weeks, rosters: current.rosters }
            : template,
        );
        setError(null);
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [structure, invalidStructure]);

  const problems = useMemo(() => (spec ? specProblems(spec) : []), [spec]);
  const dupes = useMemo(() => (spec ? duplicateAbbreviations(spec) : new Set<string>()), [spec]);

  async function create() {
    if (!spec) return;
    setCreating(true);
    setError(null);
    try {
      await api.createLeague(spec);
      // A new active franchise changes every page; a full load guarantees no page shows
      // the previous franchise from the client router cache.
      hardNavigate("/");
    } catch (e) {
      setError((e as Error).message);
      setCreating(false);
    }
  }

  function changeStructure(next: Structure) {
    setStructure(next);
    if (!structureError(next)) setLoading(true);
  }

  const set = <K extends keyof LeagueCreate>(key: K, value: LeagueCreate[K]) =>
    setSpec((s) => (s ? { ...s, [key]: value } : s));

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-24">
      <div>
        <div className="eyebrow text-gold">New league</div>
        <h1 className="font-display text-4xl font-bold uppercase tracking-wide">Create a league</h1>
        <p className="mt-1 text-sm text-mist">
          Every team is fictional and fully editable. Your new franchise becomes active when you create it.
        </p>
      </div>

      <section className="panel space-y-4 p-5" aria-label="League settings">
        <h2 className="eyebrow">League</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Name" className="lg:col-span-2">
            <input className="field-input" value={spec?.name ?? ""} maxLength={80}
              onChange={(e) => set("name", e.target.value)} disabled={!spec} />
          </Field>
          <Field label="Abbreviation">
            <input className="field-input uppercase" value={spec?.abbreviation ?? ""} maxLength={8}
              onChange={(e) => set("abbreviation", e.target.value.toUpperCase())} disabled={!spec} />
          </Field>
          <Field label="Salary cap ($M)">
            <input className="field-input" type="number" min={50} max={1000}
              value={spec ? spec.salary_cap / 1_000_000 : 255}
              onChange={(e) => set("salary_cap", Math.round(Number(e.target.value) * 1_000_000))}
              disabled={!spec} />
          </Field>
          <Field label="Regular season weeks">
            <input className="field-input" type="number" min={1} max={20} value={spec?.weeks ?? 17}
              onChange={(e) => set("weeks", Number(e.target.value))} disabled={!spec} />
          </Field>
        </div>
      </section>

      <section className="panel space-y-4 p-5" aria-label="Structure">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="eyebrow">Structure</h2>
          <p className="text-xs text-mist">Changing the structure resets team details.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-4">
          <StructureSelect label="Conferences" value={structure.conferences} max={4}
            onChange={(conferences) => changeStructure({ ...structure, conferences })} />
          <StructureSelect label="Divisions per conference" value={structure.divisions} max={4}
            onChange={(divisions) => changeStructure({ ...structure, divisions })} />
          <StructureSelect label="Teams per division" value={structure.teamsPerDivision} max={8}
            onChange={(teamsPerDivision) => changeStructure({ ...structure, teamsPerDivision })} />
          <div className="flex flex-col justify-end">
            <span className="text-xs text-mist">Total</span>
            <span className={`stat-number text-3xl ${invalidStructure ? "text-rose-300" : ""}`}
              data-testid="team-total">{totalTeams(structure)} teams</span>
          </div>
        </div>
        {invalidStructure && <p role="alert" className="text-sm text-rose-300">{invalidStructure}</p>}
      </section>

      {spec && !invalidStructure && (
        <section className={`space-y-4 ${loading ? "opacity-50" : ""}`} aria-label="Teams" aria-busy={loading}>
          {spec.conferences.map((conference, c) => (
            <div key={c} className="panel space-y-4 p-5">
              <input
                aria-label={`Conference ${c + 1} name`}
                className="w-full bg-transparent font-display text-2xl font-bold uppercase tracking-wide focus:outline-none"
                value={conference.name}
                onChange={(e) => setSpec(renameConference(spec, c, e.target.value))}
              />
              {conference.divisions.map((division, d) => (
                <div key={d} className="space-y-2">
                  <input
                    aria-label={`${conference.name} division ${d + 1} name`}
                    className="eyebrow w-full bg-transparent focus:text-chalk focus:outline-none"
                    value={division.name}
                    onChange={(e) => setSpec(renameDivision(spec, c, d, e.target.value))}
                  />
                  <ul className="space-y-2">
                    {division.teams.map((team, t) => (
                      <TeamRow
                        key={t}
                        team={team}
                        duplicate={dupes.has(team.abbreviation.toUpperCase())}
                        isMine={team.abbreviation.toUpperCase() === spec.user_team}
                        onMine={() => set("user_team", team.abbreviation.toUpperCase())}
                        onChange={(patch) => setSpec(updateTeam(spec, [c, d, t] as TeamPath, patch))}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </section>
      )}

      {spec && (
        <section className="panel space-y-3 p-5" aria-label="Rosters">
          <h2 className="eyebrow">Rosters</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["generated", "Generate fictional players", "Full 53-man rosters, contracts under the cap."],
                ["empty", "Start empty", "Teams start with no players — import rosters or sign free agents."],
              ] as const
            ).map(([value, label, hint]) => (
              <label key={value}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  spec.rosters === value ? "border-gold/50 bg-gold/[0.05]" : "border-white/10 hover:border-white/20"}`}>
                <input type="radio" name="rosters" value={value} checked={spec.rosters === value}
                  onChange={() => set("rosters", value)} className="mt-1 accent-[var(--color-gold)]" />
                <span>
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-xs text-mist">{hint}</span>
                </span>
              </label>
            ))}
          </div>
        </section>
      )}

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-ink-900/95 backdrop-blur lg:left-60">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <div className="min-w-0 flex-1 text-sm">
            {error ? (
              <span role="alert" className="text-rose-300">{error}</span>
            ) : problems.length ? (
              <span className="text-amber-200">{problems[0]}</span>
            ) : spec ? (
              <span className="text-mist">
                {totalTeams(structure)} teams · {spec.weeks} weeks · {formatMoney(spec.salary_cap)} cap · You:{" "}
                <span className="text-chalk">{spec.user_team}</span>
              </span>
            ) : null}
          </div>
          <button type="button" className="btn btn-ghost" onClick={() => router.push("/leagues")}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!spec || loading || creating || !!invalidStructure || problems.length > 0}
            onClick={create}
          >
            {creating ? "Creating league…" : "Create league"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="text-xs text-mist">{label}</span>
      {children}
    </label>
  );
}

function StructureSelect({ label, value, max, onChange }: {
  label: string; value: number; max: number; onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <select className="field-input" value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {RANGE(max).map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
    </Field>
  );
}

function TeamRow({ team, duplicate, isMine, onMine, onChange }: {
  team: TeamIdentity;
  duplicate: boolean;
  isMine: boolean;
  onMine: () => void;
  onChange: (patch: Partial<TeamIdentity>) => void;
}) {
  const label = `${team.city} ${team.nickname}`.trim() || "team";
  return (
    <li
      data-testid="builder-team"
      className={`grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3 rounded-xl border px-3 py-2 md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_5rem_minmax(0,1.2fr)_auto_auto] ${
        isMine ? "border-gold/40 bg-gold/[0.04]" : "border-white/5 bg-white/[0.02]"}`}
    >
      <TeamCrest team={{ ...team, full_name: label }} size={30} />
      <input aria-label={`City for ${label}`} className="field-input" value={team.city} maxLength={60}
        onChange={(e) => onChange({ city: e.target.value })} />
      <input aria-label={`Nickname for ${label}`} className="field-input" value={team.nickname} maxLength={60}
        onChange={(e) => onChange({ nickname: e.target.value })} />
      <input aria-label={`Abbreviation for ${label}`} aria-invalid={duplicate}
        className={`field-input uppercase ${duplicate ? "border-rose-400/70" : ""}`}
        value={team.abbreviation} maxLength={4}
        onChange={(e) => onChange({ abbreviation: e.target.value.toUpperCase() })} />
      <input aria-label={`Stadium for ${label}`} className="field-input" value={team.stadium} maxLength={80}
        onChange={(e) => onChange({ stadium: e.target.value })} />
      <span className="flex gap-1">
        <input type="color" aria-label={`Primary color for ${label}`} value={team.primary_color}
          onChange={(e) => onChange({ primary_color: e.target.value.toUpperCase() })}
          className="h-9 w-9 cursor-pointer rounded border border-white/10 bg-transparent" />
        <input type="color" aria-label={`Secondary color for ${label}`} value={team.secondary_color}
          onChange={(e) => onChange({ secondary_color: e.target.value.toUpperCase() })}
          className="h-9 w-9 cursor-pointer rounded border border-white/10 bg-transparent" />
      </span>
      <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-xs">
        <input type="radio" name="user-team" checked={isMine} onChange={onMine}
          className="accent-[var(--color-gold)]" aria-label={`Play as ${label}`} />
        <span className={isMine ? "text-gold" : "text-mist"}>{isMine ? "Your team" : "Play as"}</span>
      </label>
    </li>
  );
}
