"""Pydantic request/response models for the HTTP API."""

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

class LeagueOut(BaseModel):
    id: int
    name: str
    abbreviation: str
    salary_cap: int


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
    payroll: int
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
    year: int
    phase: str
    current_week: int  # next week to be played; weeks + 1 once the regular season is done
    weeks: int
    regular_season_complete: bool


class GameOut(BaseModel):
    id: int
    week: int
    home: TeamSummary
    away: TeamSummary
    home_score: int | None
    away_score: int | None
    status: str
    overtime: bool = False


class SimulateRequest(BaseModel):
    until: Literal["next_week", "end_of_regular_season"] = "next_week"


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


# ---------- franchise dashboard ----------

class FranchiseOut(BaseModel):
    id: int
    name: str
    league: LeagueOut
    team: TeamSummary
    season: SeasonOut


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
