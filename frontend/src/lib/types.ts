// Mirrors backend/app/schemas.py. Keep in sync when the API changes.

export const POSITIONS = [
  "QB", "RB", "FB", "WR", "TE", "OT", "OG", "C",
  "DE", "DT", "OLB", "MLB", "CB", "FS", "SS", "K", "P",
] as const;
export type Position = (typeof POSITIONS)[number];

export const POSITION_GROUPS = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "ST"] as const;
export type PositionGroup = (typeof POSITION_GROUPS)[number];

export const INJURY_STATUSES = ["healthy", "questionable", "out", "injured_reserve"] as const;
export type InjuryStatus = (typeof INJURY_STATUSES)[number];

export const DEVELOPMENT_TRAITS = ["normal", "impact", "star", "elite"] as const;
export type DevelopmentTrait = (typeof DEVELOPMENT_TRAITS)[number];

export interface League {
  id: number;
  name: string;
  abbreviation: string;
  salary_cap: number;
}

export interface TeamSummary {
  id: number;
  city: string;
  nickname: string;
  full_name: string;
  abbreviation: string;
  primary_color: string;
  secondary_color: string;
  division: string;
  conference: string;
}

export interface TeamRatings {
  overall: number;
  offense: number;
  defense: number;
  special_teams: number;
}

export interface TeamDetail extends TeamSummary {
  stadium: string;
  ratings: TeamRatings;
  roster_count: number;
  roster_max: number;
  payroll: number;
  cap_space: number;
}

export interface Contract {
  start_year: number;
  years: number;
  end_year: number;
  salary: number;
  signing_bonus: number;
}

export interface PlayerSummary {
  id: number;
  team_id: number | null;
  first_name: string;
  last_name: string;
  full_name: string;
  position: Position;
  position_group: PositionGroup;
  jersey_number: number;
  age: number;
  height_in: number;
  weight_lb: number;
  college: string;
  years_pro: number;
  overall: number;
  potential: number;
  development_trait: DevelopmentTrait;
  injury_status: InjuryStatus;
  contract: Contract | null;
  key_ratings: Record<string, number>;
}

export interface PlayerDetail extends PlayerSummary {
  ratings: Record<string, number>;
}

export interface PlayerCreate {
  first_name: string;
  last_name: string;
  position: Position;
  jersey_number: number;
  age?: number;
  height_in?: number;
  weight_lb?: number;
  college?: string;
  ratings?: Record<string, number>;
}

export type PlayerUpdate = Partial<
  Pick<
    PlayerDetail,
    | "first_name" | "last_name" | "position" | "jersey_number" | "age" | "height_in"
    | "weight_lb" | "college" | "potential" | "development_trait" | "injury_status"
  >
> & { ratings?: Record<string, number> };

export interface Season {
  id: number;
  year: number;
  phase: string;
  current_week: number;
}

export interface Game {
  id: number;
  week: number;
  home: TeamSummary;
  away: TeamSummary;
  home_score: number | null;
  away_score: number | null;
  status: string;
}

export interface StandingRow {
  team: TeamSummary;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  win_pct: number;
}

export interface DivisionStandings {
  division: string;
  conference: string;
  rows: StandingRow[];
}

export interface Franchise {
  id: number;
  name: string;
  league: League;
  team: TeamSummary;
  season: Season;
}

export interface PositionGroupSummary {
  group: PositionGroup;
  count: number;
  average_overall: number;
  starter_overall: number;
}

export interface Alert {
  level: "info" | "warning" | "critical";
  message: string;
}

export interface Dashboard {
  franchise: Franchise;
  team: TeamDetail;
  record: { wins: number; losses: number; ties: number };
  division_standings: DivisionStandings;
  upcoming_games: Game[];
  top_players: PlayerSummary[];
  position_groups: PositionGroupSummary[];
  expiring_contracts: number;
  alerts: Alert[];
}
