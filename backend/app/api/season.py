from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import Game, League, Season, User
from app.schemas import (
    DraftOut,
    DraftPickRequest,
    DraftRequest,
    DraftResult,
    FreeAgencyOut,
    FreeAgencyRequest,
    FreeAgencyResult,
    GameDetail,
    GamePlayback,
    PlayoffsOut,
    ScheduleWeek,
    SeasonOut,
    SimulateRequest,
    SimulationResult,
)
from app.services import draft as draft_service
from app.services import free_agency as free_agency_service
from app.services import games as game_service
from app.services import offseason as offseason_service
from app.services import playback as playback_service
from app.services import playoffs as playoff_service
from app.services import season as season_service
from app.services.members import user_team_id
from app.services.teams import current_season

router = APIRouter(tags=["season"])


@router.post("/seasons/{season_id}/simulate", response_model=SimulationResult)
def simulate(season_id: int, request: SimulateRequest, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Play the next week, or the rest of the regular season, with the game engine."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        weeks, played = season_service.simulate(db, season, request)
    return season_service.simulation_result(db, season, weeks, played,
                                            user_team_id(db, season.league_id, user))


@router.post("/seasons/{season_id}/advance", response_model=SeasonOut, status_code=201)
def advance(season_id: int, db: Session = Depends(get_db)):
    """Run the offseason (aging, development, retirements, contracts) and open the next
    season with free agency."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        new_season = offseason_service.advance(db, season)
    return season_service.season_view(db, new_season)


@router.post("/seasons/{season_id}/free-agency", response_model=FreeAgencyResult)
def play_free_agency(request: FreeAgencyRequest, season_id: int,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Play the next free-agency day, or every remaining day; the market closes (rookies
    fill open spots, preseason begins) after the last one."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        entries = free_agency_service.play_days(db, season, request.until)
    return free_agency_service.play_result(db, season, entries,
                                           user_team_id(db, season.league_id, user))


@router.get("/leagues/{league_id}/free-agency", response_model=FreeAgencyOut)
def free_agency(league: League = Depends(get_league), user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    """The market: free agents with asking prices, offer counts, your offers, signings."""
    return free_agency_service.market_view(db, league, user_team_id(db, league.id, user))


@router.get("/leagues/{league_id}/draft", response_model=DraftOut)
def draft(league: League = Depends(get_league), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    """The draft: order and picks, the class (as scouted), scouting reports left. The
    class is generated the first time it's needed."""
    view = draft_service.draft_view(db, league, user_team_id(db, league.id, user))
    db.commit()
    return view


@router.post("/leagues/{league_id}/draft/pick", response_model=DraftResult)
def draft_pick(request: DraftPickRequest, league: League = Depends(get_league),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Your team drafts a prospect when it's on the clock."""
    with roster_errors(db):
        pick = draft_service.user_pick(db, league, request.player_id,
                                       user_team_id(db, league.id, user))
    season = db.get(Season, pick.season_id)
    return DraftResult(season=season_service.season_view(db, season),
                       picks=[draft_service.pick_out(
                           pick, draft_service.team_count(db, league.id))])


@router.post("/seasons/{season_id}/draft", response_model=DraftResult)
def play_draft(request: DraftRequest, season_id: int, db: Session = Depends(get_db)):
    """AI teams pick until the franchise is on the clock (`my_pick`), or to the end
    (`end`, auto-picking for the franchise); then undrafted prospects fill open spots, AI
    teams cut down to 53, and the preseason begins."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "season not found")
    with roster_errors(db):
        picks = draft_service.play(db, season, request.until)
    return draft_service.play_result(db, season, picks)


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


@router.get("/games/{game_id}/playback", response_model=GamePlayback)
def playback(game_id: int, db: Session = Depends(get_db)):
    """Everything the 3D viewer needs for a game: typed play records with each scrimmage
    play's 22 players, and those players' names, numbers, positions, and speed."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "game not found")
    return playback_service.game_playback(db, game)
