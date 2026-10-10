import type { LeagueCreate, TeamIdentity } from "@/lib/types";

export const MIN_TEAMS = 4;
export const MAX_TEAMS = 40;

export interface Structure {
  conferences: number;
  divisions: number;
  teamsPerDivision: number;
}

export const DEFAULT_STRUCTURE: Structure = { conferences: 2, divisions: 4, teamsPerDivision: 4 };

export function totalTeams(s: Structure): number {
  return s.conferences * s.divisions * s.teamsPerDivision;
}

/** Why a structure can't be built, or null when it's fine (mirrors the API's rules). */
export function structureError(s: Structure): string | null {
  const total = totalTeams(s);
  if (total < MIN_TEAMS) return `A league needs at least ${MIN_TEAMS} teams (this has ${total}).`;
  if (total > MAX_TEAMS) return `A league can have at most ${MAX_TEAMS} teams (this has ${total}).`;
  if (total % 2) return `Use an even number of teams so everyone plays every week (this has ${total}).`;
  return null;
}

export function allTeams(spec: LeagueCreate): TeamIdentity[] {
  return spec.conferences.flatMap((c) => c.divisions.flatMap((d) => d.teams));
}

/** Upper-cased abbreviations used by more than one team. */
export function duplicateAbbreviations(spec: LeagueCreate): Set<string> {
  const counts = new Map<string, number>();
  for (const team of allTeams(spec)) {
    const key = team.abbreviation.trim().toUpperCase();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return new Set([...counts].filter(([, n]) => n > 1).map(([key]) => key));
}

export type TeamPath = [conference: number, division: number, team: number];

/** Immutably patch one team. Keeps user_team pointing at the same team if renamed. */
export function updateTeam(spec: LeagueCreate, [c, d, t]: TeamPath, patch: Partial<TeamIdentity>): LeagueCreate {
  const before = spec.conferences[c].divisions[d].teams[t];
  const conferences = spec.conferences.map((conf, ci) =>
    ci !== c
      ? conf
      : {
          ...conf,
          divisions: conf.divisions.map((div, di) =>
            di !== d
              ? div
              : { ...div, teams: div.teams.map((team, ti) => (ti === t ? { ...team, ...patch } : team)) },
          ),
        },
  );
  const renamed = patch.abbreviation !== undefined && before.abbreviation === spec.user_team;
  return { ...spec, conferences, user_team: renamed ? patch.abbreviation!.toUpperCase() : spec.user_team };
}

export function renameConference(spec: LeagueCreate, c: number, name: string): LeagueCreate {
  return { ...spec, conferences: spec.conferences.map((conf, i) => (i === c ? { ...conf, name } : conf)) };
}

export function renameDivision(spec: LeagueCreate, c: number, d: number, name: string): LeagueCreate {
  return {
    ...spec,
    conferences: spec.conferences.map((conf, ci) =>
      ci !== c ? conf : { ...conf, divisions: conf.divisions.map((div, di) => (di === d ? { ...div, name } : div)) },
    ),
  };
}

/** Problems to fix before the league can be created (client-side mirror of API checks). */
export function specProblems(spec: LeagueCreate): string[] {
  const problems: string[] = [];
  if (!spec.name.trim()) problems.push("Give the league a name.");
  if (!/^[A-Za-z0-9]{2,8}$/.test(spec.abbreviation)) problems.push("League abbreviation must be 2–8 letters or digits.");
  const teams = allTeams(spec);
  if (teams.some((t) => !t.city.trim() || !t.nickname.trim() || !t.stadium.trim())) {
    problems.push("Every team needs a city, nickname, and stadium.");
  }
  if (teams.some((t) => !/^[A-Za-z0-9]{2,4}$/.test(t.abbreviation))) {
    problems.push("Team abbreviations must be 2–4 letters or digits.");
  }
  const dupes = duplicateAbbreviations(spec);
  if (dupes.size) problems.push(`Abbreviations used twice: ${[...dupes].join(", ")}.`);
  if (!teams.some((t) => t.abbreviation.toUpperCase() === spec.user_team)) problems.push("Pick your team.");
  return problems;
}
