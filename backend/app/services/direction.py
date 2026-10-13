"""AI front offices' direction (docs/design/owners-and-front-offices.md §5; the rules:
domain/direction.py). Each offseason every AI team decides whether it's contending, in the
middle, or rebuilding (`decide`), and builds to match: re-signing (services/offseason.py),
free agency (services/free_agency.py) and the draft (services/draft.py). Teams members run
have none: their managers decide (on autopilot, the franchise decides like the AI).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import direction as rules
from app.domain.contracts import market_salary
from app.domain.positions import Position
from app.models import League, Owner, Player, Team, User
from app.schemas import FrontOfficeOut
from app.services.members import display_name, human_team_ids, manager_of
from app.services.serializers import team_summary
from app.services.teams import load_overrides, load_roster, team_lineup, team_ratings


def decide(db: Session, league: League, autopilot: bool = False) -> None:
    """Every AI team's direction for the coming season (members' teams too, on autopilot)."""
    from app.services.owners import ensure_owners  # (owners build on the season services)

    ensure_owners(db, league)
    humans = set() if autopilot else human_team_ids(db, league.id)
    teams = list(db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)))
    overrides = load_overrides(db, [t.id for t in teams])
    lineups = {t.id: team_lineup(load_roster(db, t.id), overrides[t.id]) for t in teams}
    rating = {tid: team_ratings(lineup).overall for tid, lineup in lineups.items()}
    ranked = sorted(rating, key=lambda tid: (-rating[tid], tid))
    priority = dict(db.execute(select(Owner.team_id, Owner.priority)
                               .where(Owner.league_id == league.id)).all())
    for team in teams:
        if team.id in humans:
            team.direction = team.direction_reasons = None
            continue
        starters = {p.id: p for players in lineups[team.id].values() for p in players}
        made = rules.decide(ranked.index(team.id) + 1, len(teams),
                            [p.age for p in starters.values()], priority.get(team.id, "build"))
        team.direction, team.direction_reasons = made.direction, made.reasons
    db.flush()


def ensure(db: Session, league: League) -> None:
    """A league from before directions (or a new one) decides them the first time they're
    needed."""
    humans = human_team_ids(db, league.id)
    if any(t.direction is None for t in league.teams if t.id not in humans):
        decide(db, league)


def of(team: Team) -> str:
    """A team's direction (the middle until it has one)."""
    return team.direction or "middle"


def raises_due(roster: list[Player], year: int, direction: str) -> int:
    """What re-signing next year's keepers will cost on top of their salaries now (the
    raises a front office plans its cap around)."""
    total = 0
    for player in roster:
        contract = player.active_contract
        if contract is None or contract.end_year != year:
            continue
        if not rules.keeps(direction, player.age + 1, player.overall):
            continue
        total += max(0, market_salary(Position(player.position), player.overall) - contract.salary)
    return total


def front_offices(db: Session, league: League) -> list[FrontOfficeOut]:
    """Every team's direction and why (a member's team: who runs it)."""
    ensure(db, league)
    out = []
    for team in sorted(league.teams, key=lambda t: t.id):
        manager = manager_of(db, team.id)
        if manager is not None:
            out.append(FrontOfficeOut(team=team_summary(team), direction=None, label=None,
                                      reasons=[], manager=display_name(db.get(User, manager))))
            continue
        out.append(FrontOfficeOut(team=team_summary(team), direction=team.direction,
                                  label=rules.DIRECTIONS.get(team.direction or "middle"),
                                  reasons=team.direction_reasons or [], manager=None))
    return out
