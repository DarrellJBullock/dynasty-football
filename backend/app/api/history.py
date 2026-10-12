from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.api.players import get_player
from app.db import get_db
from app.models import League, Player
from app.schemas import CareerOut, DynastyReport, HistoryOut
from app.services import dynasty
from app.services import history as history_service

router = APIRouter(tags=["history"])


@router.get("/leagues/{league_id}/history", response_model=HistoryOut)
def history(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Every season (champion, runner-up, awards, the franchise's record and result) and
    single-season and career records."""
    view = history_service.history_view(db, league)
    db.commit()  # awards are backfilled for seasons finished before they existed
    return view


@router.get("/leagues/{league_id}/dynasty", response_model=DynastyReport)
def dynasty_report(from_year: int = Query(...), to_year: int = Query(...),
                   league: League = Depends(get_league), db: Session = Depends(get_db)):
    """The Dynasty report for a span of up to 10 seasons: each season's result and awards,
    and the franchise's offseason after it."""
    with roster_errors(db):
        return dynasty.report(db, league, from_year, to_year)


@router.get("/players/{player_id}/career", response_model=CareerOut)
def career(player: Player = Depends(get_player), db: Session = Depends(get_db)):
    """Season-by-season regular-season stats, career totals, and awards."""
    return history_service.career(db, player)
