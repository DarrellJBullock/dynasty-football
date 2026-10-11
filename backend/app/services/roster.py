"""Roster management rules: create, edit, release, and sign players."""

from sqlalchemy.orm import Session

from app.domain.contracts import market_salary
from app.domain.positions import ROSTER_MAX, Position, available_jersey
from app.domain.ratings import ATTRIBUTES, calculate_overall
from app.models import Contract, Player, PlayerRatings, Team
from app.schemas import PlayerCreate, PlayerUpdate, SigningRequest
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.injuries import heal
from app.services.teams import current_season, load_roster, payroll

DEFAULT_RATING = 50


def contract_start_year(db: Session, team: Team) -> int:
    """The season new contracts start in: the current one, or next season once this one
    is over (offseason signings shouldn't expire at the rollover)."""
    season = current_season(db, team.league_id)
    if season is None:
        raise RosterError("league has no active season", 400)
    return season.year + 1 if season.phase == "offseason" else season.year


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

    player = new_player(
        team,
        season_year=contract_start_year(db, team),
        ratings=ratings,
        salary=salary,
        contract_years=payload.contract_years,
        first_name=payload.first_name,
        last_name=payload.last_name,
        position=payload.position.value,
        jersey_number=payload.jersey_number,
        age=payload.age,
        height_in=payload.height_in,
        weight_lb=payload.weight_lb,
        college=payload.college,
        potential=payload.potential,
        development_trait=payload.development_trait,
    )
    db.add(player)
    db.flush()
    return player


def new_player(team: Team, *, season_year: int, ratings: dict[str, int], salary: int,
               contract_years: int, potential: int | None = None, **fields) -> Player:
    """Build (not persist) a rostered player with ratings, cached OVR, and a contract.

    `fields` are Player column values (names, position, jersey_number, age, ...).
    """
    overall = calculate_overall(fields["position"], ratings)
    player = Player(
        league_id=team.league_id,
        team_id=team.id,
        **({"years_pro": 0, "injury_status": "healthy"} | fields),
        overall=overall,
        potential=max(overall, potential or overall),
        ratings=PlayerRatings(**ratings),
    )
    player.contracts.append(Contract(team_id=team.id, start_year=season_year,
                                     years=contract_years, salary=salary))
    return player


def update_player(db: Session, player: Player, payload: PlayerUpdate) -> Player:
    changes = payload.model_dump(exclude_unset=True, exclude={"ratings"})
    new_position = changes.get("position")
    if new_position is not None and new_position != player.position:
        # Leave the old position's depth chart; the player joins the new one at the bottom.
        remove_player(db, player, Position(player.position))
    if "jersey_number" in changes and player.team_id is not None:
        _check_jersey(load_roster(db, player.team_id), changes["jersey_number"], player.id)
    for field, value in changes.items():
        if value is None:
            continue
        setattr(player, field, value.value if isinstance(value, Position) else value)
    if changes.get("injury_status") == "healthy":
        heal(player)
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
    remove_player(db, player)
    player.team_id = None
    db.flush()
    return player


def sign_player(db: Session, team: Team, request: SigningRequest) -> Player:
    player = db.get(Player, request.player_id)
    if player is None or player.league_id != team.league_id:
        raise RosterError("player not found", 404)
    if player.team_id is not None:
        raise RosterError("player is under contract with another team")
    if player.retired_year is not None:
        raise RosterError("player has retired")
    roster = load_roster(db, team.id)
    _check_roster_space(roster)
    salary = request.salary if request.salary is not None else market_salary(
        Position(player.position), player.overall)
    _check_cap(team, roster, salary)

    taken = {p.jersey_number for p in roster}
    if player.jersey_number in taken:
        player.jersey_number = available_jersey(player.position, taken)
    player.team_id = team.id
    player.contracts.append(Contract(team_id=team.id, start_year=contract_start_year(db, team),
                                     years=request.years, salary=salary))
    db.flush()
    return player
