"""Injuries between games: record new ones from play logs and count down recoveries.

A player's `injury_weeks` is the number of upcoming games he misses. Statuses follow:
0 → questionable (plays; healthy after the next week), 1-3 → out, 4+ → injured reserve.
Season-ending injuries (SEASON_ENDING) don't count down; the offseason heals them.
Statuses set by hand (no `injury` description) are left for the user to change.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

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

    for event in events:  # the week's "injury" play events, in order
        player = db.get(Player, event["player"])
        if player is None:
            continue
        # A questionable player can get hurt again; the worse injury wins.
        if player.injury is None or event["weeks"] >= player.injury_weeks:
            player.injury = event["injury"]
            player.injury_weeks = event["weeks"]
            player.injury_status = status_for(event["weeks"])
    db.flush()
