"""The season together: ready check-ins, the commissioner advancing, league settings."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import League, User
from app.schemas import LeagueSettingsIn, ReadyIn, TurnOut
from app.services import league_log, turns

router = APIRouter(prefix="/leagues/{league_id}", tags=["season together"])


@router.get("/turn", response_model=TurnOut)
def turn(league: League = Depends(get_league), user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """What's next in the season, who's ready for it, and when the league advances."""
    with roster_errors(db):  # (a draft clock that ran out is settled first)
        return turns.turn_view(db, league, user)


@router.put("/ready", response_model=TurnOut)
def ready(body: ReadyIn, league: League = Depends(get_league),
          user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Say you're ready for the next step (or take it back)."""
    with roster_errors(db):
        turns.set_ready(db, league, user, body.ready)
    return turns.turn_view(db, league, user)


@router.post("/advance", response_model=TurnOut)
def advance(league: League = Depends(get_league), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """Advance one step: a week, a playoff round, the offseason, a market day, or the draft
    up to the next manager on the clock. Ready or not."""
    with roster_errors(db):
        turns.advance(db, league, user)
    return turns.turn_view(db, league, user)


@router.patch("/settings", response_model=TurnOut)
def settings(body: LeagueSettingsIn, league: League = Depends(get_league),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The draft clock and the daily advance."""
    before = turns.settings_fields(league)
    with roster_errors(db):
        turns.update_settings(db, league, body)
        changes = league_log.diff(before, turns.settings_fields(league))
        if changes:
            league_log.record(db, league.id, user, "settings", "Changed the league settings",
                              changes)
    return turns.turn_view(db, league, user)
