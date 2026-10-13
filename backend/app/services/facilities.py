"""Facilities (docs/design/staff-and-legacy.md §3): each team's training facility, medical
center and scouting department, level 1 (adds nothing) to 5.

An upgrade is paid from the staff budget the season it's bought and the new level arrives
at the next offseason (`complete_upgrades`, before development). Every level above 1 costs
upkeep each season (counted in the staff payroll, services/carousel.py); a team whose
budget can't keep its facilities up loses a level (`keep_up`). AI teams build when they
have room (`ai_upgrades`). No effect draws: they scale the staff's (domain/staff.py).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.models import Facility, League, Team
from app.schemas import FacilityOut
from app.services.errors import RosterError
from app.services.notifications import notify_team
from app.services.teams import current_season


def ensure_facilities(db: Session, league: League) -> None:
    """Every team has each facility (at level 1, to start)."""
    have = {(t, k) for t, k in db.execute(
        select(Facility.team_id, Facility.kind).join(Team, Team.id == Facility.team_id)
        .where(Team.league_id == league.id))}
    for team in league.teams:
        for kind in rules.FACILITIES:
            if (team.id, kind) not in have:
                db.add(Facility(team_id=team.id, kind=kind, level=1, upgrade_cost=0))
    db.flush()


def levels(db: Session, league: League) -> dict[int, dict[str, int]]:
    """team id -> kind -> level (made first, if the league has none yet)."""
    ensure_facilities(db, league)
    out: dict[int, dict[str, int]] = {}
    for f in db.scalars(select(Facility).join(Team, Team.id == Facility.team_id)
                        .where(Team.league_id == league.id)):
        out.setdefault(f.team_id, {})[f.kind] = f.level
    return out


def _get(db: Session, team_id: int, kind: str) -> Facility:
    facility = db.scalar(select(Facility).where(Facility.team_id == team_id,
                                                Facility.kind == kind))
    if facility is None:
        raise RosterError("No such facility.", 404)
    return facility


def upgrade(db: Session, team: Team, kind: str) -> Facility:
    """Build the next level: paid from this season's staff budget, ready next season."""
    from app.services import carousel  # (it counts facilities in the payroll)

    if kind not in rules.FACILITIES:
        raise RosterError("No such facility.", 404)
    ensure_facilities(db, db.get(League, team.league_id))
    facility = _get(db, team.id, kind)
    name = rules.FACILITIES[kind][0].lower()
    if facility.upgrade_year is not None:
        raise RosterError(f"The {name} is already being upgraded: it's ready next season.")
    if facility.level >= rules.LEVEL_MAX:
        raise RosterError(f"The {name} is already level {rules.LEVEL_MAX}.")
    season = current_season(db, team.league_id)
    year = season.year if season else 0
    cost = rules.UPGRADE_COST[facility.level + 1]
    room = carousel.budget(db, team, year).room
    if cost > room:
        raise RosterError(f"The upgrade (${cost:,}) is more than your staff budget's room "
                          f"(${room:,}).")
    facility.upgrade_year, facility.upgrade_cost = year, cost
    db.flush()
    return facility


def complete_upgrades(db: Session, league: League, year: int) -> None:
    """Upgrades bought by `year` arrive (the offseason after it)."""
    for facility in db.scalars(select(Facility).join(Team, Team.id == Facility.team_id).where(
            Team.league_id == league.id, Facility.upgrade_year.is_not(None),
            Facility.upgrade_year <= year)):
        facility.level = min(rules.LEVEL_MAX, facility.level + 1)
        facility.upgrade_year, facility.upgrade_cost = None, 0
    db.flush()


def keep_up(db: Session, league: League, year: int) -> None:
    """A team whose staff budget for `year` can't carry its facilities' upkeep loses
    levels (the highest first) until it can; a member's team is told."""
    from app.services import carousel
    from app.services.members import human_team_ids

    humans = human_team_ids(db, league.id)
    for team in sorted(league.teams, key=lambda t: t.id):
        while carousel.budget(db, team, year).room < 0:
            built = sorted((f for f in db.scalars(select(Facility).where(
                Facility.team_id == team.id)) if f.level > 1),
                key=lambda f: (-f.level, list(rules.FACILITIES).index(f.kind)))
            if not built:
                break
            worn = built[0]
            worn.level -= 1
            db.flush()
            if team.id in humans:
                notify_team(db, team.id, "staff",
                            f"Your {rules.FACILITIES[worn.kind][0].lower()} fell to level "
                            f"{worn.level}", "The staff budget couldn't keep it up.", "/staff",
                            key=f"facility-worn:{worn.id}:{year}:{worn.level}")


def ai_upgrades(db: Session, league: League, year: int, teams: list[Team]) -> None:
    """Each of these (AI) teams builds one level of its weakest facility it can afford."""
    from app.services import carousel

    current = levels(db, league)
    for team in teams:
        kind = rules.ai_upgrade(current.get(team.id, {}), carousel.budget(db, team, year).room)
        if kind is not None and _get(db, team.id, kind).upgrade_year is None:
            facility = _get(db, team.id, kind)
            facility.upgrade_year = year
            facility.upgrade_cost = rules.UPGRADE_COST[facility.level + 1]
    db.flush()


def team_facilities(db: Session, team: Team) -> list[FacilityOut]:
    ensure_facilities(db, db.get(League, team.league_id))
    out = []
    for kind, (name, duty) in rules.FACILITIES.items():
        f = _get(db, team.id, kind)
        out.append(FacilityOut(
            kind=kind, name=name, duty=duty, level=f.level,
            effect=rules.facility_effect(kind, f.level), upkeep=rules.upkeep(f.level),
            next_cost=rules.UPGRADE_COST.get(f.level + 1), upgrading=f.upgrade_year is not None,
            upgrade_effect=rules.facility_effect(kind, f.level + 1)
            if f.level < rules.LEVEL_MAX else None))
    return out
