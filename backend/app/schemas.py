"""Pydantic request/response models for the HTTP API."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

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


# ---------- season ----------

class SeasonOut(BaseModel):
    id: int
    year: int
    phase: str
    current_week: int


class GameOut(BaseModel):
    id: int
    week: int
    home: TeamSummary
    away: TeamSummary
    home_score: int | None
    away_score: int | None
    status: str


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


# ---------- franchise dashboard ----------

class FranchiseOut(BaseModel):
    id: int
    name: str
    league: LeagueOut
    team: TeamSummary
    season: SeasonOut


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
    top_players: list[PlayerSummary]
    position_groups: list[PositionGroupSummary]
    expiring_contracts: int
    alerts: list[Alert]
