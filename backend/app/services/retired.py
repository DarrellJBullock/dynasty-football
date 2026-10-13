"""Retired numbers (services/legacy.py): a team never issues one again. Kept apart so
every service that hands out jerseys can ask without importing the legacy rules."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RetiredNumber, Team


def retired_numbers(db: Session, team_id: int) -> set[int]:
    return set(db.scalars(select(RetiredNumber.number).where(RetiredNumber.team_id == team_id)))


def league_retired(db: Session, league_id: int) -> dict[int, set[int]]:
    """team id -> its retired numbers, for every team in the league."""
    out: dict[int, set[int]] = defaultdict(set)
    for team_id, number in db.execute(select(RetiredNumber.team_id, RetiredNumber.number)
                                      .join(Team, Team.id == RetiredNumber.team_id)
                                      .where(Team.league_id == league_id)):
        out[team_id].add(number)
    return out
