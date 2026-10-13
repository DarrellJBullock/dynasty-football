"""Pydantic request/response models for the HTTP API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.positions import Position, PositionGroup
from app.domain.ratings import ATTRIBUTES

Rating = Annotated[int, Field(ge=0, le=99)]
DevelopmentTrait = Literal["normal", "impact", "star", "elite"]
InjuryStatus = Literal["healthy", "questionable", "out", "injured_reserve"]


def _validate_rating_keys(value: dict[str, int] | None) -> dict[str, int] | None:
    if value is not None:
        unknown = set(value) - set(ATTRIBUTES)
        if unknown:
            raise ValueError(f"unknown rating attributes: {', '.join(sorted(unknown))}")
    return value


# ---------- league structure ----------

LeaguePlayers = Literal["men", "women"]


class LeagueOut(BaseModel):
    id: int
    name: str
    abbreviation: str
    salary_cap: int
    players: LeaguePlayers = "men"


class TeamSummary(BaseModel):
    id: int
    city: str
    nickname: str
    full_name: str
    abbreviation: str
    primary_color: str
    secondary_color: str
    division: str
    conference: str


class TeamRatings(BaseModel):
    overall: int
    offense: int
    defense: int
    special_teams: int


class TeamDetail(TeamSummary):
    stadium: str
    ratings: TeamRatings
    roster_count: int
    roster_max: int
    payroll: int  # active cap hits + dead money, this cap year
    dead_money: int = 0
    cap_space: int


# ---------- players ----------

class ContractOut(BaseModel):
    start_year: int
    years: int
    end_year: int
    salary: int
    signing_bonus: int


class PlayerSummary(BaseModel):
    id: int
    team_id: int | None
    first_name: str
    last_name: str
    full_name: str
    position: Position
    position_group: PositionGroup
    jersey_number: int
    age: int
    height_in: int
    weight_lb: int
    college: str
    years_pro: int
    overall: int
    potential: int
    development_trait: str
    injury_status: str
    injury: str | None = None  # from a simulated game
    injury_weeks: int = 0  # games still to miss (99: rest of the season)
    injury_count: int = 0  # career injuries from games
    retired_year: int | None = None
    draft_year: int | None = None
    draft_round: int | None = None
    draft_pick: int | None = None  # overall pick
    contract: ContractOut | None
    key_ratings: dict[str, int]


class PlayerDetail(PlayerSummary):
    ratings: dict[str, int]


class PlayerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=40)
    last_name: str = Field(min_length=1, max_length=40)
    position: Position
    jersey_number: int = Field(ge=0, le=99)
    age: int = Field(default=22, ge=18, le=50)
    height_in: int = Field(default=74, ge=60, le=90)
    weight_lb: int = Field(default=220, ge=140, le=400)
    college: str = Field(default="Undrafted", max_length=60)
    potential: Rating | None = None
    development_trait: DevelopmentTrait = "normal"
    # Any omitted attribute defaults to 50.
    ratings: dict[str, Rating] | None = None
    salary: int | None = Field(default=None, ge=0)
    contract_years: int = Field(default=1, ge=1, le=7)

    _check_ratings = field_validator("ratings")(_validate_rating_keys)


class PlayerUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=40)
    last_name: str | None = Field(default=None, min_length=1, max_length=40)
    position: Position | None = None
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    age: int | None = Field(default=None, ge=18, le=50)
    height_in: int | None = Field(default=None, ge=60, le=90)
    weight_lb: int | None = Field(default=None, ge=140, le=400)
    college: str | None = Field(default=None, max_length=60)
    potential: Rating | None = None
    development_trait: DevelopmentTrait | None = None
    injury_status: InjuryStatus | None = None
    # Partial: only the listed attributes change.
    ratings: dict[str, Rating] | None = None

    _check_ratings = field_validator("ratings")(_validate_rating_keys)


class SigningRequest(BaseModel):
    player_id: int
    salary: int | None = Field(default=None, ge=0)
    years: int = Field(default=1, ge=1, le=7)


# ---------- depth chart ----------

class DepthSlot(BaseModel):
    slot: Position
    unit: Literal["offense", "defense", "special_teams"]
    starters: int  # how many starters this slot fields
    customized: bool  # False = ordered by OVR
    # Starters actually fielded (skips injured players and anyone starting elsewhere).
    starter_ids: list[int]
    players: list[PlayerSummary]


class DepthChart(BaseModel):
    team: TeamDetail
    slots: list[DepthSlot]


class DepthSlotUpdate(BaseModel):
    # Full order for the slot, first string first. Players whose natural position is
    # this slot but who are omitted are appended by OVR.
    player_ids: list[int] = Field(max_length=53)


# ---------- roster import ----------

ImportMode = Literal["append", "replace"]


class ImportMessage(BaseModel):
    level: Literal["error", "warning"]
    message: str


class ImportRow(BaseModel):
    row_number: int
    status: Literal["ok", "warning", "error"]
    first_name: str
    last_name: str
    position: Position | None
    jersey_number: int | None
    age: int
    height_in: int
    weight_lb: int
    college: str
    overall: int | None
    potential: int | None
    salary: int | None
    messages: list[ImportMessage]


class ImportSummary(BaseModel):
    total: int
    valid: int
    warnings: int
    errors: int


class ImportPreview(BaseModel):
    format: str
    mode: ImportMode
    file_warnings: list[str]
    rows: list[ImportRow]
    summary: ImportSummary
    roster_before: int
    released: int  # players who would be released (replace mode)
    roster_after: int
    roster_max: int
    payroll_after: int
    salary_cap: int
    can_commit: bool  # true when every row is valid


class ImportResult(BaseModel):
    imported: int
    released: int
    skipped: int
    team: TeamDetail


# ---------- season ----------

class SeasonOut(BaseModel):
    id: int
    league_id: int
    year: int
    phase: str
    current_week: int  # next week to be played; weeks + 1 once the regular season is done
    weeks: int
    regular_season_complete: bool
    next_round: str | None = None  # name of the next playoff round to play, if any
    free_agency_day: int | None = None  # market day to play next, during free agency
    champion: "TeamSummary | None" = None
    active_job: "JobOut | None" = None  # a background sim running in this league


JobKind = Literal["sim_regular_season", "sim_playoffs", "advance_offseason",
                  "finish_free_agency", "finish_draft", "sim_seasons"]


class JobRequest(BaseModel):
    kind: JobKind
    seasons: int | None = Field(default=None, ge=1, le=10)  # sim_seasons: how many


class JobOut(BaseModel):
    """A background sim: how far it's got, and once it's over, what it did (`result` has
    the same shape as the matching synchronous endpoint's response)."""

    id: int
    league_id: int
    kind: JobKind
    params: dict | None = None  # e.g. {"seasons": 5}
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: int
    total: int
    label: str
    cancellable: bool  # stops between weeks, rounds or days
    cancel_requested: bool
    result: dict | None = None
    error: str | None = None


class GameOut(BaseModel):
    id: int
    week: int
    home: TeamSummary
    away: TeamSummary
    home_score: int | None
    away_score: int | None
    status: str
    overtime: bool = False
    stage: Literal["regular", "playoff"] = "regular"
    round_name: str | None = None  # playoff games: "Wild Card", "Championship", ...
    neutral_site: bool = False


class PlayoffSeedOut(BaseModel):
    seed: int
    team: TeamSummary
    wins: int
    losses: int
    ties: int
    division_winner: bool
    eliminated: bool


class PlayoffConference(BaseModel):
    conference: str
    seeds: list[PlayoffSeedOut]


class PlayoffRound(BaseModel):
    round: int
    name: str
    games: list[GameOut]  # empty until the round is scheduled


class PlayoffsOut(BaseModel):
    season: SeasonOut
    # projected: regular season under way (seeds as of today) · in_progress · complete
    status: Literal["projected", "in_progress", "complete"]
    conferences: list[PlayoffConference]
    rounds: list[PlayoffRound]
    champion: TeamSummary | None


class SimulateRequest(BaseModel):
    # next_week: the next regular-season week, or the next playoff round once it's over.
    until: Literal["next_week", "end_of_regular_season", "end_of_playoffs"] = "next_week"


class SimulationResult(BaseModel):
    weeks_simulated: int
    games_simulated: int
    season: SeasonOut
    # The active franchise's games from this run, oldest first.
    franchise_games: list[GameOut]


class ScheduleWeek(BaseModel):
    season: SeasonOut
    week: int
    games: list[GameOut]


class PlayOut(BaseModel):
    n: int
    quarter: int
    clock: str
    offense: str
    down: int | None
    distance: int | None
    spot: str | None  # broadcast yard line, e.g. "HFD 25"
    type: str
    text: str
    home_score: int
    away_score: int
    scoring: bool
    play_name: str | None = None  # the offense's named play (SIM_VERSION 1.3+)
    defense_name: str | None = None  # the defense's named call


class PlayerGameLine(BaseModel):
    player_id: int
    team_id: int
    name: str
    position: str
    stats: dict[str, int]  # non-zero box-score columns only


class GameDetail(BaseModel):
    game: GameOut
    season_year: int
    # Points by period, home and away; index 4+ is overtime.
    line_score: dict[Literal["home", "away"], list[int]]
    team_stats: dict[Literal["home", "away"], dict[str, int]]
    players: list[PlayerGameLine]
    scoring_plays: list[PlayOut]
    plays: list[PlayOut]
    injuries: list["GameInjury"] = []
    # An older season's game whose play-by-play was trimmed to its scoring plays and
    # injuries (services/compaction.py): `plays` holds only those.
    log_compacted: bool = False


class GameInjury(BaseModel):
    player_id: int
    team_id: int
    name: str
    position: str
    injury: str
    weeks: int  # games to miss (0: questionable; 99: season-ending)
    quarter: int
    clock: str


class StandingRow(BaseModel):
    team: TeamSummary
    wins: int
    losses: int
    ties: int
    points_for: int
    points_against: int
    win_pct: float


class DivisionStandings(BaseModel):
    division: str
    conference: str
    rows: list[StandingRow]


# ---------- custom leagues & teams ----------

HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
TeamAbbreviation = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{2,4}$")]
MIN_LEAGUE_TEAMS = 4
MAX_LEAGUE_TEAMS = 40


class TeamIdentity(BaseModel):
    city: str = Field(min_length=1, max_length=60)
    nickname: str = Field(min_length=1, max_length=60)
    abbreviation: TeamAbbreviation
    primary_color: HexColor
    secondary_color: HexColor
    stadium: str = Field(min_length=1, max_length=80)

    @field_validator("abbreviation")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class TeamUpdate(BaseModel):
    city: str | None = Field(default=None, min_length=1, max_length=60)
    nickname: str | None = Field(default=None, min_length=1, max_length=60)
    abbreviation: TeamAbbreviation | None = None
    primary_color: HexColor | None = None
    secondary_color: HexColor | None = None
    stadium: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("abbreviation")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class DivisionSpec(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    teams: list[TeamIdentity] = Field(min_length=1, max_length=8)


class ConferenceSpec(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    abbreviation: str = Field(min_length=2, max_length=4)
    divisions: list[DivisionSpec] = Field(min_length=1, max_length=4)


class LeagueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    abbreviation: str = Field(pattern=r"^[A-Za-z0-9]{2,8}$")
    salary_cap: int = Field(default=255_000_000, ge=50_000_000, le=1_000_000_000)
    season_year: int = Field(default=2026, ge=1900, le=2200)
    weeks: int = Field(default=17, ge=1, le=20)
    rosters: Literal["generated", "empty"] = "generated"
    # Who plays: generated players get names and builds to match.
    players: LeaguePlayers = "men"
    conferences: list[ConferenceSpec] = Field(min_length=1, max_length=4)
    # Abbreviation of the team the user will control.
    user_team: str
    franchise_name: str | None = Field(default=None, max_length=80)
    seed: int | None = None

    @model_validator(mode="after")
    def _check_structure(self) -> "LeagueCreate":
        teams = self.teams()
        if not MIN_LEAGUE_TEAMS <= len(teams) <= MAX_LEAGUE_TEAMS:
            raise ValueError(f"a league needs {MIN_LEAGUE_TEAMS}-{MAX_LEAGUE_TEAMS} teams "
                             f"(got {len(teams)})")
        if len(teams) % 2:
            raise ValueError(f"a league needs an even number of teams (got {len(teams)}) "
                             "so every team plays every week")
        seen: set[str] = set()
        for team in teams:
            if team.abbreviation in seen:
                raise ValueError(f"team abbreviation {team.abbreviation} is used twice")
            seen.add(team.abbreviation)
        self.user_team = self.user_team.upper()
        if self.user_team not in seen:
            raise ValueError(f"user_team {self.user_team} is not one of the league's teams")
        return self

    def teams(self) -> list[TeamIdentity]:
        return [t for c in self.conferences for d in c.divisions for t in d.teams]


# ---------- season stats ----------

class LeaderRow(BaseModel):
    player_id: int
    name: str
    position: str
    team: TeamSummary | None  # current team, or last team played for if now a free agent
    games: int
    value: int
    stats: dict[str, int]  # the category's supporting columns


class LeaderCategory(BaseModel):
    key: str
    label: str
    leaders: list[LeaderRow]


class LeadersOut(BaseModel):
    season: SeasonOut
    categories: list[LeaderCategory]


class GameLogRow(BaseModel):
    game_id: int
    week: int
    opponent: TeamSummary
    home: bool
    result: str  # "W 26-17"
    stats: dict[str, int]


class PlayerSeasonStats(BaseModel):
    player: PlayerSummary
    team: TeamSummary | None
    season: SeasonOut
    games: int
    totals: dict[str, int]
    game_log: list[GameLogRow]


class TeamSeasonRow(BaseModel):
    team: TeamSummary
    games: int
    wins: int
    losses: int
    ties: int
    points_for: int
    points_against: int
    total_yds: int
    pass_yds: int
    rush_yds: int
    first_downs: int
    turnovers: int
    sacks_allowed: int
    penalties: int
    penalty_yds: int
    time_of_possession: int
    third_down_att: int
    third_down_conv: int
    # Defense: what opponents did against this team.
    yds_allowed: int
    pass_yds_allowed: int
    rush_yds_allowed: int
    takeaways: int
    sacks: int


# ---------- franchise dashboard ----------

class FranchiseOut(BaseModel):
    id: int
    name: str
    league: LeagueOut
    team: TeamSummary
    season: SeasonOut
    role: Literal["commissioner", "manager"] = "manager"  # the user's role in the league


class FranchiseListItem(FranchiseOut):
    is_active: bool
    team_count: int


class PositionGroupSummary(BaseModel):
    group: PositionGroup
    count: int
    average_overall: int
    starter_overall: int


class Alert(BaseModel):
    level: Literal["info", "warning", "critical"]
    message: str


class Record(BaseModel):
    wins: int
    losses: int
    ties: int


class RecapSigning(BaseModel):
    player: PlayerSummary
    salary: int
    years: int


class RecapMove(BaseModel):
    player: PlayerSummary
    before: int
    after: int


class RecapRetirement(BaseModel):
    player: PlayerSummary
    team: TeamSummary | None  # None: retired as a free agent


class OffseasonRecap(BaseModel):
    """The offseason before `year`, for one team (plus the league's notable retirements)."""
    from_year: int
    year: int
    retired: list[PlayerSummary]
    departed: list[PlayerSummary]  # contract expired and no cap room to re-sign
    re_signed: list[RecapSigning]
    signed: list[RecapSigning]  # free agents who filled open spots
    rookies: list[PlayerSummary]  # draft picks (by pick), then undrafted free agents
    risers: list[RecapMove]
    decliners: list[RecapMove]
    league_retirements: list[RecapRetirement]


class Dashboard(BaseModel):
    franchise: FranchiseOut
    team: TeamDetail
    record: Record
    division_standings: DivisionStandings
    upcoming_games: list[GameOut]
    recent_games: list[GameOut]
    top_players: list[PlayerSummary]
    position_groups: list[PositionGroupSummary]
    expiring_contracts: int
    alerts: list[Alert]
    injury_report: list[PlayerSummary] = []
    offseason: OffseasonRecap | None = None  # shown until the first game of the season


# ---------- contracts ----------


class ContractTerms(BaseModel):
    salary: int
    years: int


class ExpiringContract(BaseModel):
    player: PlayerSummary
    asking: ContractTerms  # at the length he prefers
    re_signed: ContractOut | None  # the new deal, once he has signed one


class TeamContracts(BaseModel):
    season: SeasonOut
    window_open: bool  # re-signing is open (the season is over)
    salary_cap: int
    payroll: int  # active contracts now
    next_year_payroll: int  # already committed to next season
    dead_money: list["DeadMoneyOut"] = []  # charges for this season and later
    expiring: list[ExpiringContract]
    players: list[PlayerSummary]  # everyone under contract, highest salary first


class DeadMoneyOut(BaseModel):
    player_id: int
    name: str
    position: str
    year: int
    amount: int
    reason: str  # released | traded | retired


class ReSignOffer(BaseModel):
    salary: int = Field(ge=750_000, le=100_000_000)
    years: int = Field(ge=1, le=5)


class NegotiationResult(BaseModel):
    accepted: bool
    message: str
    counter: ContractTerms | None  # his price for the offered length, if he said no
    player: PlayerSummary


# ---------- free agency ----------


class FreeAgentRow(BaseModel):
    player: PlayerSummary
    asking: ContractTerms  # his price at the length he prefers
    offers: int  # pending offers, yours included
    my_offer: ContractTerms | None
    leading: bool | None  # your offer is currently his best (None: no offer)


class MarketSigning(BaseModel):
    player: PlayerSummary
    team: TeamSummary
    salary: int
    years: int
    day: int


class FreeAgencyOut(BaseModel):
    season: SeasonOut
    open: bool
    day: int | None  # market day to play next
    days: int
    demand: float | None  # share of his price a player needs today
    open_spots: int  # on your roster
    cap_space: int  # yours, now
    players: list[FreeAgentRow]  # best first
    signings: list[MarketSigning]  # this offseason's market, latest first


class FreeAgencyRequest(BaseModel):
    until: Literal["next_day", "end"] = "next_day"


class FreeAgencyResult(BaseModel):
    season: SeasonOut
    signings: list[MarketSigning]
    mine: list[MarketSigning]


# ---------- draft ----------


class ProspectRow(BaseModel):
    """A draft prospect as the franchise sees him: a projection until scouted."""
    id: int
    full_name: str
    position: Position
    age: int
    college: str
    height_in: int
    weight_lb: int
    projected: int  # projected OVR (exact once scouted)
    low: int
    high: int
    grade: str  # potential grade, A+ to D
    scouted: bool
    overall: int | None  # true values, once scouted
    potential: int | None


class DraftPickOut(BaseModel):
    round: int
    number: int  # overall
    pick_in_round: int
    team: TeamSummary  # who picks
    original_team: TeamSummary | None = None  # set if the pick was traded ("via")
    player: PlayerSummary | None


class DraftOut(BaseModel):
    season: SeasonOut
    year: int  # the class
    status: Literal["upcoming", "live", "complete"]
    picks: list[DraftPickOut]
    on_the_clock: int | None
    my_team_id: int | None
    my_next_pick: int | None
    prospects: list[ProspectRow]  # still available, best projection first
    scouting_left: int
    roster_count: int
    roster_max: int
    # When the manager on the clock runs out of time (a draft with several managers).
    clock_ends_at: datetime | None = None


class DraftPickRequest(BaseModel):
    player_id: int


class DraftRequest(BaseModel):
    until: Literal["my_pick", "end"] = "my_pick"


class DraftResult(BaseModel):
    season: SeasonOut
    picks: list[DraftPickOut]


# ---------- trades ----------


class TradeAssetOut(BaseModel):
    kind: Literal["player", "pick"]
    id: int
    label: str
    value: float  # trade value, as the AI sees it
    player: PlayerSummary | None = None
    round: int | None = None  # picks
    year: int | None = None
    projected_number: int | None = None


class TradeAssets(BaseModel):
    players: list[TradeAssetOut]  # most valuable first
    picks: list[TradeAssetOut]


class TradeItem(BaseModel):
    kind: Literal["player", "pick"]
    id: int
    label: str


class TradeOut(BaseModel):
    id: int
    partner: TeamSummary
    season_phase: str
    week: int
    sent: list[TradeItem]  # from the franchise's side
    received: list[TradeItem]


class TradeCenter(BaseModel):
    season: SeasonOut
    closed_reason: str | None  # why trades are closed, if they are
    deadline_week: int
    draft_year: int  # picks in this draft can be traded
    partners: list[TeamSummary]
    partner: TeamSummary | None
    partner_manager: str | None = None  # the partner's manager (an offer), or None (the AI)
    managed: list[int] = []  # partners another member runs
    mine: TradeAssets
    theirs: TradeAssets
    history: list[TradeOut]  # latest first
    offers: list["TradeOfferOut"] = []  # yours, open first; and, for a commissioner, reviews
    review_hours: int = 0  # the commissioner's veto window (0: none)


class TradeOfferItem(BaseModel):
    kind: Literal["player", "pick"]
    id: int
    label: str


class TradeOfferOut(BaseModel):
    """An offer between managers, with what each side gives."""
    id: int
    from_team: TeamSummary
    to_team: TeamSummary
    from_manager: str
    to_manager: str
    gives: list[TradeOfferItem]  # from_team sends
    gets: list[TradeOfferItem]  # from_team receives
    note: str | None
    status: Literal["pending", "accepted", "rejected", "withdrawn", "countered", "expired",
                    "invalid", "review", "vetoed"]
    reason: str | None
    direction: Literal["incoming", "outgoing", "other"]  # for the viewer's team
    parent_id: int | None
    created_at: datetime
    expires_at: datetime
    review_ends_at: datetime | None


class TradeOfferIn(BaseModel):
    proposal: "TradeProposal"
    note: str | None = Field(default=None, max_length=200)


class VetoIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class TradeProposal(BaseModel):
    partner_id: int
    send_players: list[int] = []
    send_picks: list[int] = []
    receive_players: list[int] = []
    receive_picks: list[int] = []


class TradeEvaluation(BaseModel):
    acceptable: bool
    balance: float  # what the AI gets ÷ what it needs (1.0+ = yes), capped at 2
    message: str
    problems: list[str]  # cap, roster, or trade-window issues
    value_in: float
    value_needed: float


class TradeResult(BaseModel):
    accepted: bool
    evaluation: TradeEvaluation
    trade: TradeOut | None


# ---------- history ----------


class AwardOut(BaseModel):
    award: str  # mvp | opoy | dpoy | oroy | droy
    label: str
    year: int
    player_id: int
    name: str
    position: str
    team: TeamSummary | None
    summary: str


class SeasonHistory(BaseModel):
    season_id: int
    year: int
    phase: str
    complete: bool
    champion: TeamSummary | None
    runner_up: TeamSummary | None
    awards: list[AwardOut]
    franchise_record: Record | None
    franchise_result: str  # "Won the championship", "Lost in the Divisional", ...


class RecordRow(BaseModel):
    player_id: int
    name: str
    position: str
    team: str | None  # current team (abbreviation)
    year: int | None  # single-season records
    value: int
    games: int
    retired: bool


class RecordCategory(BaseModel):
    key: str
    label: str
    single_season: list[RecordRow]
    career: list[RecordRow]
    single_game: list[RecordRow] = []  # (a team's record book)


class HistoryOut(BaseModel):
    seasons: list[SeasonHistory]  # latest first
    records: list[RecordCategory]  # regular season, all seasons in the league


class CareerSeason(BaseModel):
    year: int
    team: TeamSummary
    games: int
    stats: dict[str, int]


class CareerOut(BaseModel):
    player_id: int
    seasons: list[CareerSeason]
    games: int
    totals: dict[str, int]
    awards: list[AwardOut]
    hall_of_fame: int | None = None  # the year he was inducted
    retired_by: list[str] = []  # teams that retired his number (nicknames)


# ---------- legacy (services/legacy.py) ----------


class HallOfFamer(BaseModel):
    player_id: int
    name: str
    position: str
    year: int  # the class
    team: "TeamSummary | None"  # where he played the most games
    score: float
    case: str  # "3× MVP · 2 titles · 41,250 pass yds · 12 seasons"
    inducted: bool
    retired_year: int | None


class RetiredNumberOut(BaseModel):
    team: "TeamSummary"
    number: int
    player_id: int
    name: str
    year: int


class HallOfFameOut(BaseModel):
    members: list[HallOfFamer]  # latest class first
    ballot_year: int | None
    near_misses: list[HallOfFamer]  # the latest ballot's best cases that didn't get in
    retired_numbers: list[RetiredNumberOut]
    eligible_after: int  # seasons after retiring
    bar: float  # the score a case needs


class RetireCandidate(BaseModel):
    player_id: int
    name: str
    position: str
    number: int
    hall_of_fame: bool


class TeamRecordsOut(BaseModel):
    team: "TeamSummary"
    records: list[RecordCategory]  # games for this team only
    hall_of_famers: list[HallOfFamer]
    retired_numbers: list[RetiredNumberOut]
    retire_candidates: list[RetireCandidate]  # (its manager's choices; empty for others)


class RetireNumberIn(BaseModel):
    player_id: int


# ---------- staff (services/staff.py) ----------


StaffRole = Literal["head_coach", "offensive_coordinator", "defensive_coordinator", "scout",
                    "trainer"]


class StaffCareer(BaseModel):
    seasons: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    playoff_wins: int = 0
    titles: int = 0
    coach_of_the_year: int = 0


class StaffOut(BaseModel):
    id: int
    role: StaffRole
    role_label: str  # "Offensive coordinator"
    duty: str  # what the role does, in a line
    name: str
    age: int
    rating: int  # 40-99
    specialty: str | None  # e.g. "QB" for an OC
    effect: str = ""  # what they do at this rating, in a line
    salary: int
    contract_end: int  # the last season of the contract
    team: "TeamSummary | None"
    career: StaffCareer  # seasons with any team, in this league


class CoachingItem(BaseModel):
    role: StaffRole
    role_label: str
    name: str
    rating: int
    specialty: str | None


class PlayerCoachingOut(BaseModel):
    """What his team's staff do for a player (none: a free agent, or retired)."""
    items: list[CoachingItem]  # his coordinator, head coach and trainer
    phase: Literal["growing", "peak", "declining"] | None  # where he is in his career
    development: str | None = None  # "With these coaches he grows 18% faster this offseason…"
    injuries: str | None = None  # "Injured players come back 15% sooner."


class FacilityOut(BaseModel):
    kind: Literal["training", "medical", "scouting"]
    name: str  # "Training facility"
    duty: str  # what it does, in a line
    level: int  # 1-5
    effect: str  # what it adds at this level
    upkeep: int  # a season
    next_cost: int | None  # to build the next level (None: at the top)
    upgrading: bool  # the next level arrives next season
    upgrade_effect: str | None  # what the next level would add


class StaffBudget(BaseModel):
    year: int
    budget: int  # the league's staff budget a season
    payroll: int  # salaries and dead money this season
    dead_money: int  # owed to staff the team let go
    room: int  # budget - payroll


class TeamStaffOut(BaseModel):
    team: "TeamSummary"
    members: list[StaffOut]  # head coach first
    payroll: int  # the staff's salaries a season
    budget: StaffBudget | None = None
    vacancies: list[StaffRole] = []  # jobs open
    facilities: list[FacilityOut] = []


class StaffMarketOut(BaseModel):
    year: int
    candidates: list[StaffOut]  # out of work, by role then rating; salary: what they'd sign for
    budget: StaffBudget | None  # the viewer's team's


class HireIn(BaseModel):
    staff_id: int
    years: int = 3


class ExtendIn(BaseModel):
    years: int = 3


class CoachOfTheYear(BaseModel):
    year: int
    staff_id: int
    name: str
    team: "TeamSummary"
    wins: int
    losses: int
    ties: int


class CoachesOut(BaseModel):
    head_coaches: list[StaffOut]  # most career wins first
    coach_of_the_year: list[CoachOfTheYear]  # latest first


# ---------- playback (3D) ----------
# Play events as the engine writes them (app/sim/resolve.py, engine.py): the contract
# between the simulation and the 3D choreographer. Ids are player ids; negative ids are
# stand-ins for empty depth-chart spots.


class _Event(BaseModel):
    model_config = {"populate_by_name": True}


class KickoffEvent(_Event):
    t: Literal["kickoff"]
    kicker: int
    touchback: bool
    return_spot: int = Field(alias="return")  # receiving team's yard line after the return
    returner: int | None = None  # (SIM_VERSION 1.2+)
    # (SIM_VERSION 1.4+) a squib or onside kick; who recovered an onside kick, and whether
    # it was the kicking team.
    kind: Literal["normal", "squib", "onside"] = "normal"
    recovered: bool | None = None
    recovered_by: int | None = None


class PuntEvent(_Event):
    t: Literal["punt"]
    punter: int
    yards: int  # gross
    touchback: bool
    fair_catch: bool = False
    return_yards: int = Field(alias="return")
    returner: int | None = None


class FieldGoalEvent(_Event):
    t: Literal["field_goal"]
    kicker: int
    distance: int
    good: bool


class ExtraPointEvent(_Event):
    t: Literal["extra_point"]
    kicker: int
    good: bool


class TwoPointEvent(_Event):
    t: Literal["two_point"]
    good: bool


class HandoffEvent(_Event):
    t: Literal["handoff"]
    to: int
    direction: str  # inside | outside


class RushEvent(_Event):
    t: Literal["rush"]
    player: int
    yards: int


class ScrambleEvent(_Event):
    t: Literal["scramble"]
    qb: int
    yards: int


class KneelEvent(_Event):
    t: Literal["kneel"]
    qb: int
    yards: int


class DropbackEvent(_Event):
    t: Literal["dropback"]
    qb: int
    depth: str  # screen | short | medium | deep


class PressureEvent(_Event):
    t: Literal["pressure"]


class SackEvent(_Event):
    t: Literal["sack"]
    qb: int
    by: int
    yards: int  # negative


class PassEvent(_Event):
    t: Literal["pass"]
    qb: int
    target: int | None
    result: Literal["complete", "incomplete", "interception", "throwaway"]
    air: int
    yards: int


class InterceptionEvent(_Event):
    t: Literal["interception"]
    by: int
    return_yards: int = Field(alias="return")


class PassDefendedEvent(_Event):
    t: Literal["pass_defended"]
    by: int


class TackleEvent(_Event):
    t: Literal["tackle"]
    by: list[int]


class FumbleEvent(_Event):
    t: Literal["fumble"]
    player: int
    forced_by: int
    lost: bool


class PenaltyEvent(_Event):
    t: Literal["penalty"]
    team: str  # abbreviation of the penalized team
    kind: str  # a key of app/sim/penalties.py NAMES (holding, offside, face_mask, ...)
    yards: int  # as enforced (half the distance to the goal at most)
    player: int | None = None
    automatic_first: bool = False  # defensive holding, illegal contact, DPI, personal fouls


class InjuryEvent(_Event):
    t: Literal["injury"]
    player: int
    team: str
    injury: str
    weeks: int


PlayEvent = Annotated[
    KickoffEvent | PuntEvent | FieldGoalEvent | ExtraPointEvent | TwoPointEvent
    | HandoffEvent | RushEvent | ScrambleEvent | KneelEvent | DropbackEvent | PressureEvent
    | SackEvent | PassEvent | InterceptionEvent | PassDefendedEvent | TackleEvent
    | FumbleEvent | PenaltyEvent | InjuryEvent,
    Field(discriminator="t"),
]


class Personnel(BaseModel):
    offense: list[int]  # 11: QB, RB, WR×3, TE, OT×2, OG×2, C
    defense: list[int]  # 11: DE×2, DT×2, OLB×(2/1/0), MLB, CB×(2/3/4), FS, SS
    package: str  # base | nickel | dime


class PlaybackPlay(BaseModel):
    n: int
    quarter: int
    clock: str
    offense: str  # abbreviation with the ball (the kicking team on kickoffs)
    side: Literal["home", "away"]
    down: int | None
    distance: int | None
    ball_on: int | None  # yards from the offense's own goal line
    call: dict | None
    defense: dict | None
    result: dict
    events: list[PlayEvent]
    elapsed: int
    score: dict[str, int]
    text: str
    personnel: Personnel | None  # scrimmage plays only
    approximate: bool = False  # personnel rebuilt from today's depth charts (old logs)
    play_name: str | None = None  # the named offensive play (SIM_VERSION 1.3+)
    defense_name: str | None = None  # the named defensive call
    # (SIM_VERSION 1.5+) each side's timeouts left at the snap, and the game seconds the
    # play ran (the clock at the snap minus at the whistle).
    timeouts: dict[str, int] | None = None
    seconds: int | None = None


class PlaybackPlayer(BaseModel):
    id: int  # negative: a stand-in
    name: str
    short_name: str
    number: int
    position: str
    team_id: int
    speed: int
    height_in: int = 74
    weight_lb: int = 230


class GamePlayback(BaseModel):
    game: "GameOut"
    sim_version: str | None
    approximate: bool  # some plays' lineups were rebuilt (the game predates SIM_VERSION 1.2)
    players: list[PlaybackPlayer]
    plays: list[PlaybackPlay]
    # Play-by-play wasn't kept for this older game: nothing to watch (`plays` is empty).
    log_compacted: bool = False


# ---------- playbook ----------

class OffensivePlayOut(BaseModel):
    key: str
    name: str
    category: Literal["run", "quick", "intermediate", "deep", "play_action", "screen", "special"]
    formation: str
    kind: Literal["run", "pass", "punt", "field_goal", "kneel"]
    description: str
    direction: Literal["inside", "outside"] | None
    depth: Literal["screen", "short", "medium", "deep"] | None
    play_action: bool
    targets: tuple[float, float, float, float, float] | None  # WR1, WR2, WR3, TE, RB


class DefensivePlayOut(BaseModel):
    key: str
    name: str
    category: Literal["zone", "man", "pressure", "situational"]
    shell: str
    coverage: Literal["man", "zone"]
    blitz: bool
    description: str
    package: Literal["base", "nickel", "dime"] | None


class PlaybookOut(BaseModel):
    offense: list[OffensivePlayOut]
    defense: list[DefensivePlayOut]


# ---------- coach mode ----------

class CoachLook(BaseModel):
    """What the other side shows at the line."""
    package: Literal["base", "nickel", "dime"] | None = None  # the defense's personnel
    safeties: Literal["two_high", "single_high", "none"] | None = None  # (maybe disguised)
    blitz: bool | None = None  # a blitz showing (maybe disguised)
    formation: str | None = None  # the offense's formation


class AudibleOption(BaseModel):
    key: str
    name: str


class FatigueLine(BaseModel):
    player_id: int
    name: str  # "K. Quarles"
    position: str
    team: str  # abbreviation
    energy: int  # 0-100 (100: fresh)
    resting: bool  # on the sideline until he recovers


class CoachSituation(BaseModel):
    # Which call the user makes: a play (offense / defense), a kicking decision, or, at the
    # line, whether to audible.
    role: Literal["offense", "defense", "kickoff", "conversion", "audible"]
    quarter: int
    clock: str  # before any runoff, e.g. "2:05"
    seconds: int
    clock_running: bool  # time runs off before the snap unless a timeout is called
    possession: Literal["home", "away"]
    offense: str  # abbreviation with the ball
    down: int
    distance: int
    ball_on: int  # yards from the offense's own goal line
    spot: str  # broadcast yard line, e.g. "HFD 25"
    score: dict[str, int]
    timeouts: dict[str, int]
    # The AI's call: a playbook key, or a kickoff (normal / squib / onside) or conversion
    # (kick / two) choice.
    suggestion: str
    suggestion_name: str
    suggested_package: Literal["base", "nickel", "dime"] | None
    # At the line: for which side, the call made, the look, and the audibles to switch to
    # (answer with the audible's key, or "keep").
    audible_for: Literal["offense", "defense"] | None = None
    called: AudibleOption | None = None
    look: CoachLook | None = None
    audibles: list[AudibleOption] = []
    # Before a snap: each side's most tired players still in the game.
    fatigue: list[FatigueLine] = []


class CoachStateOut(BaseModel):
    game: "GameOut"
    team: TeamSummary  # the team the user coaches
    side: Literal["home", "away"]
    status: Literal["in_progress", "final"]
    autopilot: bool  # the AI is calling the rest of the game
    calls: int  # calls made so far
    situation: CoachSituation | None  # None once the game is over
    plays: list[PlayOut]
    new_plays: int  # how many of `plays` the last request played
    season: "SeasonOut"


class CoachCallIn(BaseModel):
    play: str  # a playbook key: an offensive play on offense, a defensive call on defense
    package: Literal["base", "nickel", "dime"] | None = None  # defense only
    timeout: bool = False  # call a timeout before the snap


class CoachAutoIn(BaseModel):
    scope: Literal["play", "drive", "game"]


class NextGameOut(BaseModel):
    game: "GameOut | None"  # the franchise's game this week, if it hasn't been played
    coaching: bool  # the user has started coaching it


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str  # what other members see (the email's first part until one's set)
    has_league: bool  # a new account goes to the league builder first


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Enter a display name.")
        return value


MemberRole = Literal["commissioner", "manager"]


class MemberOut(BaseModel):
    id: int
    display_name: str
    role: MemberRole
    team: TeamSummary | None  # None: a commissioner who doesn't run a team
    is_you: bool
    joined_at: datetime


class InviteOut(BaseModel):
    id: int
    created_at: datetime
    expires_at: datetime
    uses: int


class InviteCreated(InviteOut):
    token: str  # shown once: only its hash is kept


class MembersOut(BaseModel):
    league: LeagueOut
    you: MemberOut
    members: list[MemberOut]
    invites: list[InviteOut]  # open links (commissioners only; empty for managers)
    open_teams: list[TeamSummary]
    shared_at: datetime | None = None  # the read-only public link, since (None: none)


class ShareLinkOut(BaseModel):
    token: str  # shown once: only its hash is kept
    shared_at: datetime


class PublicLeagueOut(BaseModel):
    league: LeagueOut
    season: SeasonOut
    teams: list[TeamSummary]


class RoleChange(BaseModel):
    role: MemberRole


class InviteToken(BaseModel):
    token: str = Field(min_length=1, max_length=100)


class InvitePreview(BaseModel):
    league: LeagueOut
    commissioner: str  # display name
    member_count: int
    open_teams: list[TeamSummary]
    already_member: bool
    your_team: TeamSummary | None  # if already a member running a team


class JoinRequest(InviteToken):
    team_id: int


class TurnMember(BaseModel):
    member_id: int
    display_name: str
    team: TeamSummary
    ready: bool
    is_you: bool


class TurnOut(BaseModel):
    """The season together: what's next, who's ready for it, and when it happens."""
    step: str  # what advancing plays next, e.g. "Week 3"
    step_key: str
    managers: list[TurnMember]  # members who run a team
    all_ready: bool
    can_advance: bool  # the viewer is a commissioner
    draft_clock_minutes: int
    advance_minute_utc: int | None  # the daily advance (minutes after midnight UTC)
    next_advance_at: datetime | None
    pick_clock_ends_at: datetime | None  # the draft: when the manager up runs out of time
    trade_review_hours: int = 0  # trades between managers wait for a veto (0: they don't)
    staff_budget: int = 20_000_000  # each team's staff budget a season


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str | None  # a page in the app
    league: str | None  # the league's name
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]  # latest first


class UnreadOut(BaseModel):
    unread: int


class MarkReadIn(BaseModel):
    ids: list[int] | None = None  # (none: all of them)


class NotificationKind(BaseModel):
    kind: str
    label: str
    email: bool


class NotificationSettingsOut(BaseModel):
    kinds: list[NotificationKind]


class NotificationSettingsIn(BaseModel):
    email: list[str]  # the kinds to email


class ReadyIn(BaseModel):
    ready: bool


class LeagueSettingsIn(BaseModel):
    draft_clock_minutes: int | None = None
    advance_minute_utc: int | None = None  # (send null to turn the daily advance off)
    trade_review_hours: int | None = None
    staff_budget: int | None = None  # each team's staff budget a season (whole dollars)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class AccountDeletion(BaseModel):
    password: str = Field(max_length=128)


class ResetRequest(BaseModel):
    email: str = Field(max_length=254)


class PasswordResetIn(BaseModel):
    token: str = Field(max_length=128)
    password: str = Field(max_length=128)


class DynastySeason(BaseModel):
    """One season of a Dynasty report: how it went, and the franchise's offseason after."""
    season: SeasonHistory
    offseason: OffseasonRecap | None  # (none yet for the latest season)


class DynastyReport(BaseModel):
    from_year: int
    to_year: int
    seasons: list[DynastySeason]  # oldest first


class GamePlanIn(BaseModel):
    offense: list[str] = Field(max_length=100)  # the plays in the plan
    defense: list[str] = Field(max_length=100)  # the calls in the plan
    tendencies: dict[str, int] = {}  # each -2..2 (missing: 0)
    # Coach Mode: up to three plays (calls) from the plan to switch to at the line.
    offense_audibles: list[str] = Field(default=[], max_length=10)
    defense_audibles: list[str] = Field(default=[], max_length=10)


class PlanRequirement(BaseModel):
    side: Literal["offense", "defense"]
    label: str  # "an inside run"
    keys: list[str]  # any one of these keeps the plan valid


class GamePlanOut(BaseModel):
    team_id: int
    custom: bool  # saved by the user (otherwise drawn from the roster)
    offense: list[str]
    defense: list[str]
    tendencies: dict[str, int]
    offense_audibles: list[str]
    defense_audibles: list[str]
    suggested: dict[str, int]  # the roster-based plan's tendencies
    offense_choices: list[str]
    defense_choices: list[str]
    tendency_labels: dict[str, str]
    required: list[PlanRequirement]
