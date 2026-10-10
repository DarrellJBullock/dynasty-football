"""Team-level calculations: lineup, team ratings, payroll."""

from collections import defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.positions import (
    DEFENSE,
    OFFENSE,
    ROSTER_MAX,
    SPECIAL_TEAMS,
    STARTERS,
    Position,
)
from app.models import Player, Season, Team
from app.schemas import TeamDetail, TeamRatings
from app.services.serializers import team_summary

UNAVAILABLE = {"out", "injured_reserve"}


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


def starting_lineup(players: list[Player]) -> dict[Position, list[Player]]:
    """Best available players at each starting slot (by OVR) until depth charts exist."""
    by_position: dict[Position, list[Player]] = defaultdict(list)
    for player in players:
        if player.injury_status not in UNAVAILABLE:
            by_position[Position(player.position)].append(player)
    return {
        position: sorted(by_position[position], key=lambda p: -p.overall)[:count]
        for position, count in STARTERS.items()
    }


def _unit_rating(lineup: dict[Position, list[Player]], unit: set[Position]) -> int:
    overalls = [p.overall for pos, starters in lineup.items() if pos in unit for p in starters]
    return round(mean(overalls)) if overalls else 0


def team_ratings(players: list[Player]) -> TeamRatings:
    lineup = starting_lineup(players)
    offense = _unit_rating(lineup, OFFENSE)
    defense = _unit_rating(lineup, DEFENSE)
    special = _unit_rating(lineup, SPECIAL_TEAMS)
    overall = round(0.45 * offense + 0.45 * defense + 0.10 * special)
    return TeamRatings(overall=overall, offense=offense, defense=defense, special_teams=special)


def payroll(players: list[Player]) -> int:
    return sum(c.salary for p in players if (c := p.active_contract) is not None)


def team_detail(team: Team, players: list[Player]) -> TeamDetail:
    total = payroll(players)
    return TeamDetail(
        **team_summary(team).model_dump(),
        stadium=team.stadium,
        ratings=team_ratings(players),
        roster_count=len(players),
        roster_max=ROSTER_MAX,
        payroll=total,
        cap_space=team.league.salary_cap - total,
    )
