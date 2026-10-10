"""Roster management rules: create, edit, release, and sign players."""

from sqlalchemy.orm import Session

from app.domain.contracts import market_salary
from app.domain.positions import ROSTER_MAX, Position, available_jersey
from app.domain.ratings import ATTRIBUTES, calculate_overall
from app.models import Contract, Player, PlayerRatings, Team
from app.schemas import PlayerCreate, PlayerUpdate, SigningRequest
from app.services.teams import current_season, load_roster, payroll

DEFAULT_RATING = 50


class RosterError(Exception):
    """A roster rule was violated. Routes translate this to an HTTP error."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _season_year(db: Session, team: Team) -> int:
    season = current_season(db, team.league_id)
    if season is None:
        raise RosterError("league has no active season", 400)
    return season.year


def _check_roster_space(roster: list[Player]) -> None:
    if len(roster) >= ROSTER_MAX:
        raise RosterError(f"roster is full ({ROSTER_MAX} players); release a player first")


def _check_jersey(roster: list[Player], number: int, exclude_id: int | None = None) -> None:
    holder = next((p for p in roster if p.jersey_number == number and p.id != exclude_id), None)
    if holder is not None:
        raise RosterError(f"jersey #{number} is already worn by {holder.full_name}")


def _check_cap(team: Team, roster: list[Player], salary: int) -> None:
    if payroll(roster) + salary > team.league.salary_cap:
        raise RosterError("signing would exceed the salary cap")


def _recalculate_overall(player: Player) -> None:
    player.overall = calculate_overall(player.position, player.ratings.as_dict())


def create_player(db: Session, team: Team, payload: PlayerCreate) -> Player:
    roster = load_roster(db, team.id)
    _check_roster_space(roster)
    _check_jersey(roster, payload.jersey_number)

    ratings = {name: DEFAULT_RATING for name in ATTRIBUTES} | (payload.ratings or {})
    overall = calculate_overall(payload.position, ratings)
    salary = payload.salary if payload.salary is not None else market_salary(
        Position(payload.position), overall)
    _check_cap(team, roster, salary)

    player = Player(
        league_id=team.league_id,
        team_id=team.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        position=payload.position.value,
        jersey_number=payload.jersey_number,
        age=payload.age,
        height_in=payload.height_in,
        weight_lb=payload.weight_lb,
        college=payload.college,
        years_pro=0,
        overall=overall,
        potential=max(overall, payload.potential or overall),
        development_trait=payload.development_trait,
        injury_status="healthy",
        ratings=PlayerRatings(**ratings),
    )
    player.contracts.append(Contract(team_id=team.id, start_year=_season_year(db, team),
                                     years=payload.contract_years, salary=salary))
    db.add(player)
    db.flush()
    return player


def update_player(db: Session, player: Player, payload: PlayerUpdate) -> Player:
    changes = payload.model_dump(exclude_unset=True, exclude={"ratings"})
    if "jersey_number" in changes and player.team_id is not None:
        _check_jersey(load_roster(db, player.team_id), changes["jersey_number"], player.id)
    for field, value in changes.items():
        if value is None:
            continue
        setattr(player, field, value.value if isinstance(value, Position) else value)
    for name, value in (payload.ratings or {}).items():
        setattr(player.ratings, name, value)
    _recalculate_overall(player)
    player.potential = max(player.potential, player.overall)
    db.flush()
    return player


def release_player(db: Session, player: Player) -> Player:
    if player.team_id is None:
        raise RosterError("player is already a free agent")
    for contract in player.contracts:
        contract.is_active = False
    player.team_id = None
    db.flush()
    return player


def sign_player(db: Session, team: Team, request: SigningRequest) -> Player:
    player = db.get(Player, request.player_id)
    if player is None or player.league_id != team.league_id:
        raise RosterError("player not found", 404)
    if player.team_id is not None:
        raise RosterError("player is under contract with another team")
    roster = load_roster(db, team.id)
    _check_roster_space(roster)
    salary = request.salary if request.salary is not None else market_salary(
        Position(player.position), player.overall)
    _check_cap(team, roster, salary)

    taken = {p.jersey_number for p in roster}
    if player.jersey_number in taken:
        player.jersey_number = available_jersey(player.position, taken)
    player.team_id = team.id
    player.contracts.append(Contract(team_id=team.id, start_year=_season_year(db, team),
                                     years=request.years, salary=salary))
    db.flush()
    return player
