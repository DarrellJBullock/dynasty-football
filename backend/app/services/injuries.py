"""Injuries between games: record new ones from play logs and count down recoveries.

A player's `injury_weeks` is the number of upcoming games he misses. Statuses follow:
0 → questionable (plays; healthy after the next week), 1-3 → out, 4+ → injured reserve.
Season-ending injuries (SEASON_ENDING) don't count down; the offseason heals them.
Statuses set by hand (no `injury` description) are left for the user to change.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.staff import layoff
from app.models import Player
from app.sim.injuries import SEASON_ENDING

INJURED_RESERVE_WEEKS = 4


def status_for(weeks: int) -> str:
    if weeks <= 0:
        return "questionable"
    return "injured_reserve" if weeks >= INJURED_RESERVE_WEEKS else "out"


def heal(player: Player) -> None:
    player.injury_status = "healthy"
    player.injury = None
    player.injury_weeks = 0


def _trainers(db: Session, league_id: int) -> dict:
    from app.models import League
    from app.services import (
        facilities,
        staff,  # (staff builds on the season services)
    )

    league = db.get(League, league_id)
    crew = staff.by_team(db, league)
    built = facilities.levels(db, league)
    return {team_id: (staff.coach(roles.get("trainer")), built.get(team_id, {}).get("medical", 1))
            for team_id, roles in crew.items()}


def after_week(db: Session, league_id: int, events: list[dict]) -> None:
    """Called once per week (or playoff round) after its games: everyone already hurt is a
    week closer to returning, then this week's injuries are recorded."""
    hurt = db.scalars(select(Player).where(Player.league_id == league_id,
                                           Player.injury.is_not(None)))
    for player in hurt:
        if player.injury_weeks >= SEASON_ENDING:
            continue  # out until the offseason
        if player.injury_weeks > 1:
            player.injury_weeks -= 1
            player.injury_status = status_for(player.injury_weeks)
        else:
            heal(player)

    trainers = _trainers(db, league_id) if events else {}
    for event in events:  # the week's "injury" play events, in order
        player = db.get(Player, event["player"])
        if player is None:
            continue
        player.injury_count = (player.injury_count or 0) + 1
        # His team's trainer gets him back sooner (services/staff.py); the play log keeps
        # the injury as it happened.
        trainer, medical = trainers.get(player.team_id, (None, 1))
        weeks = layoff(event["weeks"], trainer, SEASON_ENDING, medical)
        # A questionable player can get hurt again; the worse injury wins.
        if player.injury is None or weeks >= player.injury_weeks:
            player.injury = event["injury"]
            player.injury_weeks = weeks
            player.injury_status = status_for(weeks)
    db.flush()
