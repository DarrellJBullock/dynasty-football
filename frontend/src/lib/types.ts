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
  injury?: string | null; // from a simulated game
  injury_weeks?: number; // games still to miss (99: rest of the season)
  retired_year?: number | null; // last season played
  draft_year?: number | null;
  draft_round?: number | null;
  draft_pick?: number | null; // overall
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
  /** Next week to be played; weeks + 1 once the regular season is done. */
  current_week: number;
  weeks: number;
  regular_season_complete: boolean;
  /** Name of the next playoff round to play ("Wild Card", ...), if any. */
  next_round: string | null;
  champion: TeamSummary | null;
  /** Market day to play next, during free agency. */
  free_agency_day?: number | null;
}

export interface Game {
  id: number;
  week: number;
  home: TeamSummary;
  away: TeamSummary;
  home_score: number | null;
  away_score: number | null;
  status: string;
  overtime: boolean;
  stage: "regular" | "playoff";
  round_name: string | null;
  neutral_site: boolean;
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
  recent_games: Game[];
  top_players: PlayerSummary[];
  position_groups: PositionGroupSummary[];
  expiring_contracts: number;
  alerts: Alert[];
  injury_report?: PlayerSummary[];
  offseason?: OffseasonRecap | null; // shown until the first game of the season
}

export interface RecapSigning {
  player: PlayerSummary;
  salary: number;
  years: number;
}

export interface RecapMove {
  player: PlayerSummary;
  before: number;
  after: number;
}

export interface OffseasonRecap {
  from_year: number;
  year: number;
  retired: PlayerSummary[];
  departed: PlayerSummary[];
  re_signed: RecapSigning[];
  signed: RecapSigning[];
  rookies: PlayerSummary[];
  risers: RecapMove[];
  decliners: RecapMove[];
  league_retirements: { player: PlayerSummary; team: TeamSummary | null }[];
}

export type ImportMode = "append" | "replace";
export type ImportFormat = "csv" | "xlsx" | "json";

export interface ImportRow {
  row_number: number;
  status: "ok" | "warning" | "error";
  first_name: string;
  last_name: string;
  position: Position | null;
  jersey_number: number | null;
  age: number;
  height_in: number;
  weight_lb: number;
  college: string;
  overall: number | null;
  potential: number | null;
  salary: number | null;
  messages: { level: "error" | "warning"; message: string }[];
}

export interface ImportPreview {
  format: ImportFormat;
  mode: ImportMode;
  file_warnings: string[];
  rows: ImportRow[];
  summary: { total: number; valid: number; warnings: number; errors: number };
  roster_before: number;
  released: number;
  roster_after: number;
  roster_max: number;
  payroll_after: number;
  salary_cap: number;
  can_commit: boolean;
}

export interface ImportResult {
  imported: number;
  released: number;
  skipped: number;
  team: TeamDetail;
}

export type Unit = "offense" | "defense" | "special_teams";

export interface DepthSlot {
  slot: Position;
  unit: Unit;
  starters: number;
  customized: boolean;
  /** Starters actually fielded: skips injured players and anyone starting elsewhere. */
  starter_ids: number[];
  players: PlayerSummary[];
}

export interface DepthChart {
  team: TeamDetail;
  slots: DepthSlot[];
}

export interface TeamIdentity {
  city: string;
  nickname: string;
  abbreviation: string;
  primary_color: string;
  secondary_color: string;
  stadium: string;
}

export type TeamUpdate = Partial<TeamIdentity>;

export interface DivisionSpec {
  name: string;
  teams: TeamIdentity[];
}

export interface ConferenceSpec {
  name: string;
  abbreviation: string;
  divisions: DivisionSpec[];
}

export interface LeagueCreate {
  name: string;
  abbreviation: string;
  salary_cap: number;
  season_year: number;
  weeks: number;
  rosters: "generated" | "empty";
  conferences: ConferenceSpec[];
  user_team: string;
  franchise_name?: string | null;
  seed?: number | null;
}

export interface FranchiseListItem extends Franchise {
  is_active: boolean;
  team_count: number;
}

export type SimulateUntil = "next_week" | "end_of_regular_season" | "end_of_playoffs";

export interface SimulationResult {
  weeks_simulated: number;
  games_simulated: number;
  season: Season;
  /** The active franchise's games from this run, oldest first. */
  franchise_games: Game[];
}

export interface ScheduleWeek {
  season: Season;
  week: number;
  games: Game[];
}

export interface PlayOut {
  n: number;
  quarter: number;
  clock: string;
  offense: string;
  down: number | null;
  distance: number | null;
  spot: string | null;
  type: string;
  text: string;
  home_score: number;
  away_score: number;
  scoring: boolean;
}

export interface PlayerGameLine {
  player_id: number;
  team_id: number;
  name: string;
  position: string;
  stats: Record<string, number>;
}

export interface GameDetail {
  game: Game;
  season_year: number;
  line_score: { home: number[]; away: number[] };
  team_stats: { home?: Record<string, number>; away?: Record<string, number> };
  players: PlayerGameLine[];
  scoring_plays: PlayOut[];
  plays: PlayOut[];
  injuries?: GameInjury[];
}

export interface GameInjury {
  player_id: number;
  team_id: number;
  name: string;
  position: Position;
  injury: string;
  weeks: number; // games to miss (0: questionable; 99: season-ending)
  quarter: number;
  clock: string;
}

export interface LeaderRow {
  player_id: number;
  name: string;
  position: Position;
  team: TeamSummary | null;
  games: number;
  value: number;
  stats: Record<string, number>;
}

export interface LeaderCategory {
  key: string;
  label: string;
  leaders: LeaderRow[];
}

export interface LeadersOut {
  season: Season;
  categories: LeaderCategory[];
}

export interface GameLogRow {
  game_id: number;
  week: number;
  opponent: TeamSummary;
  home: boolean;
  result: string;
  stats: Record<string, number>;
}

export interface PlayerSeasonStats {
  player: PlayerSummary;
  team: TeamSummary | null;
  season: Season;
  games: number;
  totals: Record<string, number>;
  game_log: GameLogRow[];
}

export interface TeamSeasonRow {
  team: TeamSummary;
  games: number;
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  total_yds: number;
  pass_yds: number;
  rush_yds: number;
  first_downs: number;
  turnovers: number;
  sacks_allowed: number;
  penalties: number;
  penalty_yds: number;
  time_of_possession: number;
  third_down_att: number;
  third_down_conv: number;
  yds_allowed: number;
  pass_yds_allowed: number;
  rush_yds_allowed: number;
  takeaways: number;
  sacks: number;
}

export interface PlayoffSeed {
  seed: number;
  team: TeamSummary;
  wins: number;
  losses: number;
  ties: number;
  division_winner: boolean;
  eliminated: boolean;
}

export interface PlayoffConference {
  conference: string;
  seeds: PlayoffSeed[];
}

export interface PlayoffRound {
  round: number;
  name: string;
  games: Game[];
}

export interface PlayoffsOut {
  season: Season;
  status: "projected" | "in_progress" | "complete";
  conferences: PlayoffConference[];
  rounds: PlayoffRound[];
  champion: TeamSummary | null;
}

export interface ContractTerms {
  salary: number;
  years: number;
}

export interface ExpiringContract {
  player: PlayerSummary;
  asking: ContractTerms; // at the length he prefers
  re_signed: Contract | null; // the new deal, once he has signed one
}

export interface TeamContracts {
  season: Season;
  window_open: boolean; // re-signing is open (the season is over)
  salary_cap: number;
  payroll: number;
  next_year_payroll: number;
  expiring: ExpiringContract[];
  players: PlayerSummary[]; // everyone under contract, highest salary first
}

export interface NegotiationResult {
  accepted: boolean;
  message: string;
  counter: ContractTerms | null;
  player: PlayerSummary;
}

export interface FreeAgentRow {
  player: PlayerSummary;
  asking: ContractTerms; // his price at the length he prefers
  offers: number; // pending offers, yours included
  my_offer: ContractTerms | null;
  leading: boolean | null; // your offer is currently his best
}

export interface MarketSigning {
  player: PlayerSummary;
  team: TeamSummary;
  salary: number;
  years: number;
  day: number;
}

export interface FreeAgencyOut {
  season: Season;
  open: boolean;
  day: number | null;
  days: number;
  demand: number | null; // share of his price a player needs today
  open_spots: number;
  cap_space: number;
  players: FreeAgentRow[];
  signings: MarketSigning[];
}

export interface FreeAgencyResult {
  season: Season;
  signings: MarketSigning[];
  mine: MarketSigning[];
}

export type FreeAgencyUntil = "next_day" | "end";

/** A draft prospect as the franchise sees him: a projection until scouted. */
export interface ProspectRow {
  id: number;
  full_name: string;
  position: Position;
  age: number;
  college: string;
  height_in: number;
  weight_lb: number;
  projected: number;
  low: number;
  high: number;
  grade: string; // potential, A+ to D
  scouted: boolean;
  overall: number | null; // the truth, once scouted
  potential: number | null;
}

export interface DraftPickOut {
  round: number;
  number: number;
  pick_in_round: number;
  team: TeamSummary;
  player: PlayerSummary | null;
}

export interface DraftOut {
  season: Season;
  year: number;
  status: "upcoming" | "live" | "complete";
  picks: DraftPickOut[];
  on_the_clock: number | null;
  my_team_id: number | null;
  my_next_pick: number | null;
  prospects: ProspectRow[];
  scouting_left: number;
  roster_count: number;
  roster_max: number;
}

export interface DraftResult {
  season: Season;
  picks: DraftPickOut[];
}

export type DraftUntil = "my_pick" | "end";
