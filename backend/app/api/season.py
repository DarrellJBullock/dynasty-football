from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import Game, League, Season
from app.schemas import (
    GameDetail,
    PlayoffsOut,
    ScheduleWeek,
    SeasonOut,
    SimulateRequest,
    SimulationResult,
)
from app.services import games as game_service
from app.services import offseason as offseason_service
from app.services import playoffs as playoff_service
from app.services import season as season_service
from app.services.dashboard import current_franchise
from app.services.serializers import game_out
from app.services.teams import current_season

router = APIRouter(tags=["season"])


@router.post("/seasons/{season_id}/simulate", response_model=SimulationResult)
def simulate(season_id: int, request: SimulateRequest, db: Session = Depends(get_db)):
    """Play the next week, or the rest of the regular season, with the game engine."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        weeks, played = season_service.simulate(db, season, request)
    franchise = current_franchise(db)
    team_id = franchise.team_id if franchise and franchise.league_id == season.league_id else None
    mine = [game_out(g) for g in played if team_id in (g.home_team_id, g.away_team_id)]
    return SimulationResult(
        weeks_simulated=weeks, games_simulated=len(played),
        season=season_service.season_view(db, season),
        franchise_games=mine)


@router.post("/seasons/{season_id}/advance", response_model=SeasonOut, status_code=201)
def advance(season_id: int, db: Session = Depends(get_db)):
    """Run the offseason (aging, development, retirements, contracts, rookies) and start
    the next season."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        new_season = offseason_service.advance(db, season)
    return season_service.season_view(db, new_season)


@router.get("/leagues/{league_id}/schedule", response_model=ScheduleWeek)
def schedule(week: int | None = Query(None, ge=1), league: League = Depends(get_league),
             db: Session = Depends(get_db)):
    """One week of the current season (defaults to the next week to be played)."""
    season = current_season(db, league.id)
    if season is None:
        raise HTTPException(404, "league has no season")
    return game_service.schedule_week(db, season, week)


@router.get("/leagues/{league_id}/playoffs", response_model=PlayoffsOut)
def playoff_bracket(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Seeds and bracket: projected from standings during the regular season, then live."""
    season = current_season(db, league.id)
    if season is None:
        raise HTTPException(404, "league has no season")
    return playoff_service.playoffs_view(db, season)


@router.get("/games/{game_id}", response_model=GameDetail)
def game(game_id: int, db: Session = Depends(get_db)):
    """Scoreboard, line score, team and player stats, scoring summary, play-by-play."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "game not found")
    return game_service.game_detail(db, game)
