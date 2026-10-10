"""Team-level calculations: depth chart lineup, team ratings, payroll."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.depth_chart import build_chart, starting_lineup, unit_rating
from app.domain.positions import DEFENSE, OFFENSE, ROSTER_MAX, SPECIAL_TEAMS, Position
from app.models import DepthChartEntry, Player, Season, Team
from app.schemas import TeamDetail, TeamRatings
from app.services.serializers import team_summary


def load_roster(db: Session, team_id: int) -> list[Player]:
    stmt = (
        select(Player)
        .where(Player.team_id == team_id)
        .options(selectinload(Player.ratings), selectinload(Player.contracts))
        .order_by(Player.overall.desc(), Player.id)
    )
    return list(db.scalars(stmt))


def current_season(db: Session, league_id: int) -> Season | None:
    stmt = select(Season).where(Season.league_id == league_id).order_by(Season.year.desc())
    return db.scalars(stmt).first()


Overrides = dict[Position, list[int]]


def load_overrides(db: Session, team_ids: Iterable[int]) -> dict[int, Overrides]:
    """Saved depth chart orders, keyed by team then slot."""
    ids = list(team_ids)
    result: dict[int, Overrides] = {team_id: {} for team_id in ids}
    if not ids:
        return result
    entries = db.scalars(
        select(DepthChartEntry)
        .where(DepthChartEntry.team_id.in_(ids))
        .order_by(DepthChartEntry.team_id, DepthChartEntry.slot, DepthChartEntry.depth)
    )
    for entry in entries:
        result[entry.team_id].setdefault(Position(entry.slot), []).append(entry.player_id)
    return result


def team_lineup(players: list[Player], overrides: Overrides) -> dict[Position, list[Player]]:
    return starting_lineup(build_chart(players, overrides))


def team_ratings(lineup: dict[Position, list[Player]]) -> TeamRatings:
    offense = unit_rating(lineup, OFFENSE)
    defense = unit_rating(lineup, DEFENSE)
    special = unit_rating(lineup, SPECIAL_TEAMS)
    overall = round(0.45 * offense + 0.45 * defense + 0.10 * special)
    return TeamRatings(overall=overall, offense=offense, defense=defense, special_teams=special)


def payroll(players: list[Player]) -> int:
    return sum(c.salary for p in players if (c := p.active_contract) is not None)


def team_detail(team: Team, players: list[Player], overrides: Overrides) -> TeamDetail:
    total = payroll(players)
    return TeamDetail(
        **team_summary(team).model_dump(),
        stadium=team.stadium,
        ratings=team_ratings(team_lineup(players, overrides)),
        roster_count=len(players),
        roster_max=ROSTER_MAX,
        payroll=total,
        cap_space=team.league.salary_cap - total,
    )
