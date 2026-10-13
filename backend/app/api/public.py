"""The read-only public link (services/sharing.py): what anyone with a league's link sees,
without an account. Only reads, and only what's public: standings, the schedule, box
scores and the Watch page, the playoffs, stats, and history (never contracts)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Game, League, Season
from app.schemas import (
    DivisionStandings,
    GameDetail,
    GamePlayback,
    HistoryOut,
    LeadersOut,
    PlayoffsOut,
    PublicLeagueOut,
    ScheduleWeek,
    TeamSeasonRow,
)
from app.services import games, league_stats, playback, playoffs, sharing
from app.services import history as history_service
from app.services.errors import RosterError
from app.services.season import season_view
from app.services.serializers import league_out, team_summary
from app.services.standings import league_standings
from app.services.teams import current_season

router = APIRouter(prefix="/public/{token}", tags=["public"])


def shared_league(token: str, db: Session = Depends(get_db)) -> League:
    try:
        return sharing.league_for(db, token)
    except RosterError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc


def _season(db: Session, league: League) -> Season:
    season = current_season(db, league.id)
    if season is None:
        raise HTTPException(404, "league has no season")
    return season


def _game(db: Session, league: League, game_id: int) -> Game:
    game = db.get(Game, game_id)
    if game is None or game.season.league_id != league.id:
        raise HTTPException(404, "game not found")
    return game


@router.get("", response_model=PublicLeagueOut)
def league(league: League = Depends(shared_league), db: Session = Depends(get_db)):
    """The league, its season, and its teams."""
    return PublicLeagueOut(league=league_out(league), season=season_view(db, _season(db, league)),
                           teams=[team_summary(t) for t in league.teams])


@router.get("/standings", response_model=list[DivisionStandings])
def standings(league: League = Depends(shared_league), db: Session = Depends(get_db)):
    return league_standings(db, league, _season(db, league))


@router.get("/schedule", response_model=ScheduleWeek)
def schedule(week: int | None = Query(None, ge=1), league: League = Depends(shared_league),
             db: Session = Depends(get_db)):
    return games.schedule_week(db, _season(db, league), week)


@router.get("/playoffs", response_model=PlayoffsOut)
def playoff_bracket(league: League = Depends(shared_league), db: Session = Depends(get_db)):
    return playoffs.playoffs_view(db, _season(db, league))


@router.get("/games/{game_id}", response_model=GameDetail)
def game(game_id: int, league: League = Depends(shared_league), db: Session = Depends(get_db)):
    return games.game_detail(db, _game(db, league, game_id))


@router.get("/games/{game_id}/playback", response_model=GamePlayback)
def game_playback(game_id: int, league: League = Depends(shared_league),
                  db: Session = Depends(get_db)):
    return playback.game_playback(db, _game(db, league, game_id))


@router.get("/leaders", response_model=LeadersOut)
def leaders(category: str | None = None, limit: int = Query(5, ge=1, le=50),
            league: League = Depends(shared_league), db: Session = Depends(get_db)):
    if category is not None and category not in league_stats.CATEGORIES:
        raise HTTPException(422, f"unknown category {category!r}")
    keys = [category] if category else list(league_stats.CATEGORIES)
    return league_stats.leaders(db, _season(db, league), keys, limit)


@router.get("/team-stats", response_model=list[TeamSeasonRow])
def team_stats(league: League = Depends(shared_league), db: Session = Depends(get_db)):
    return league_stats.team_season(db, _season(db, league))


@router.get("/history", response_model=HistoryOut)
def history(league: League = Depends(shared_league), db: Session = Depends(get_db)):
    view = history_service.history_view(db, league)
    db.commit()  # (awards are backfilled for seasons finished before they existed)
    return view
