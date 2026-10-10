import type {
  Dashboard,
  DepthChart,
  DepthSlot,
  LeagueCreate,
  PlayerDetail,
  PlayerSummary,
  Position,
  PositionGroup,
  TeamDetail,
  TeamIdentity,
  TeamSummary,
  Unit,
} from "@/lib/types";

export const team: TeamSummary = {
  id: 1,
  city: "Hartford",
  nickname: "Ironclads",
  full_name: "Hartford Ironclads",
  abbreviation: "HFD",
  primary_color: "#1F3A5F",
  secondary_color: "#C9A227",
  division: "ATL North",
  conference: "Atlantic Conference",
};

export const opponent: TeamSummary = {
  ...team,
  id: 2,
  city: "Albuquerque",
  nickname: "Roadrunners",
  full_name: "Albuquerque Roadrunners",
  abbreviation: "ABQ",
};

export const teamDetail: TeamDetail = {
  ...team,
  stadium: "Foundry Field",
  ratings: { overall: 79, offense: 78, defense: 80, special_teams: 82 },
  roster_count: 53,
  roster_max: 53,
  payroll: 239_680_000,
  cap_space: 15_320_000,
};

const GROUPS: Record<string, PositionGroup> = {
  QB: "QB", RB: "RB", FB: "RB", WR: "WR", TE: "TE", OT: "OL", OG: "OL", C: "OL",
  DE: "DL", DT: "DL", OLB: "LB", MLB: "LB", CB: "DB", FS: "DB", SS: "DB", K: "ST", P: "ST",
};

let nextId = 100;

export function makePlayer(overrides: Partial<PlayerSummary> = {}): PlayerSummary {
  const position = overrides.position ?? "QB";
  const first = overrides.first_name ?? "Test";
  const last = overrides.last_name ?? `Player${nextId}`;
  return {
    id: nextId++,
    team_id: 1,
    first_name: first,
    last_name: last,
    full_name: `${first} ${last}`,
    position,
    position_group: GROUPS[position] ?? "QB",
    jersey_number: 10,
    age: 25,
    height_in: 74,
    weight_lb: 220,
    college: "Lakeshore State",
    years_pro: 3,
    overall: 75,
    potential: 80,
    development_trait: "normal",
    injury_status: "healthy",
    contract: { start_year: 2026, years: 2, end_year: 2027, salary: 5_000_000, signing_bonus: 0 },
    key_ratings: { throw_accuracy: 80, throw_power: 78, awareness: 70 },
    ...overrides,
  };
}

export function makePlayerDetail(overrides: Partial<PlayerSummary> = {}): PlayerDetail {
  const ratings = Object.fromEntries(
    [
      "speed", "acceleration", "strength", "agility", "stamina", "toughness", "awareness",
      "throw_power", "throw_accuracy", "carrying", "ball_carrier_vision", "elusiveness",
      "catching", "route_running", "run_blocking", "pass_blocking", "tackling", "pass_rush",
      "block_shedding", "man_coverage", "zone_coverage", "play_recognition", "kick_power",
      "kick_accuracy",
    ].map((name) => [name, 60]),
  );
  return { ...makePlayer(overrides), ratings };
}

export const dashboard: Dashboard = {
  franchise: {
    id: 1,
    name: "Ironclads Dynasty",
    league: { id: 1, name: "Dynasty Football League", abbreviation: "DFL", salary_cap: 255_000_000 },
    team,
    season: { id: 1, year: 2026, phase: "preseason", current_week: 1 },
  },
  team: teamDetail,
  record: { wins: 0, losses: 0, ties: 0 },
  division_standings: {
    division: "ATL North",
    conference: "Atlantic Conference",
    rows: [
      { team, wins: 0, losses: 0, ties: 0, points_for: 0, points_against: 0, win_pct: 0 },
      { team: opponent, wins: 0, losses: 0, ties: 0, points_for: 0, points_against: 0, win_pct: 0 },
    ],
  },
  upcoming_games: [
    { id: 1, week: 1, home: team, away: opponent, home_score: null, away_score: null, status: "scheduled" },
    { id: 2, week: 2, home: opponent, away: team, home_score: null, away_score: null, status: "scheduled" },
  ],
  top_players: [
    makePlayer({ first_name: "Terrell", last_name: "Stroud", position: "CB", overall: 86 }),
    makePlayer({ first_name: "Keegan", last_name: "Quarles", position: "QB", overall: 82 }),
  ],
  position_groups: [
    { group: "QB", count: 3, average_overall: 69, starter_overall: 82 },
    { group: "WR", count: 6, average_overall: 71, starter_overall: 75 },
  ],
  expiring_contracts: 21,
  alerts: [{ level: "info", message: "21 contract(s) expire after this season." }],
};

const SLOT_UNITS: [Position, Unit, number][] = [
  ["QB", "offense", 1], ["RB", "offense", 1], ["FB", "offense", 0], ["WR", "offense", 3],
  ["TE", "offense", 1], ["OT", "offense", 2], ["OG", "offense", 2], ["C", "offense", 1],
  ["DE", "defense", 2], ["DT", "defense", 2], ["OLB", "defense", 2], ["MLB", "defense", 1],
  ["CB", "defense", 2], ["FS", "defense", 1], ["SS", "defense", 1],
  ["K", "special_teams", 1], ["P", "special_teams", 1],
];

/** A depth chart with every slot; pass players / starters for the slots you care about. */
export function makeDepthChart(
  slots: Partial<Record<Position, Partial<DepthSlot>>> = {},
  teamOverrides: Partial<TeamDetail> = {},
): DepthChart {
  return {
    team: { ...teamDetail, ...teamOverrides },
    slots: SLOT_UNITS.map(([slot, unit, starters]) => ({
      slot,
      unit,
      starters,
      customized: false,
      starter_ids: [],
      players: [],
      ...slots[slot],
    })),
  };
}

/** A small valid 4-team league spec for builder tests. */
function specTeam(abbreviation: string, overrides: Partial<TeamIdentity> = {}): TeamIdentity {
  return {
    city: `City ${abbreviation}`, nickname: `Nick ${abbreviation}`, abbreviation,
    primary_color: "#112233", secondary_color: "#445566", stadium: "Field", ...overrides,
  };
}

export function makeSpec(overrides: Partial<LeagueCreate> = {}): LeagueCreate {
  return {
    name: "Test League", abbreviation: "TST", salary_cap: 255_000_000, season_year: 2026,
    weeks: 17, rosters: "generated", user_team: "AAA",
    conferences: [{
      name: "Alpha Conference", abbreviation: "ALP",
      divisions: [
        { name: "ALP North", teams: [specTeam("AAA"), specTeam("BBB")] },
        { name: "ALP South", teams: [specTeam("CCC"), specTeam("DDD")] },
      ],
    }],
    ...overrides,
  };
}
