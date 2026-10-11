from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.franchise import get_franchise
from app.db import get_db
from app.models import Franchise, Game
from app.schemas import CoachAutoIn, CoachCallIn, CoachStateOut, NextGameOut
from app.services import coach as coach_service
from app.services.serializers import game_out
from app.services.teams import current_season

router = APIRouter(tags=["coach"])


def get_game(game_id: int, db: Session = Depends(get_db)) -> Game:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "game not found")
    return game


@router.get("/franchise/next-game", response_model=NextGameOut)
def next_game(franchise: Franchise = Depends(get_franchise), db: Session = Depends(get_db)):
    """The franchise's game this week (or playoff round), if it hasn't been played, and
    whether the user has started coaching it."""
    season = current_season(db, franchise.league_id)
    game = coach_service.next_game(db, season) if season else None
    coaching = bool(game and coach_service.coached_game(db, game))
    return NextGameOut(game=game_out(game) if game else None, coaching=coaching)


@router.get("/games/{game_id}/coach", response_model=CoachStateOut)
def coach_state(game: Game = Depends(get_game), db: Session = Depends(get_db)):
    """The coached game: the next call to make (with the AI's suggestion) and every play."""
    coached = coach_service.coached_game(db, game)
    if coached is None:
        raise HTTPException(404, "you aren't coaching this game")
    with roster_errors(db):  # the replay may reach the final whistle and store the game
        return coach_service.state(db, coached)


@router.post("/games/{game_id}/coach", response_model=CoachStateOut)
def start_coaching(game: Game = Depends(get_game), db: Session = Depends(get_db)):
    """Coach the franchise's next game (or pick up where you left off)."""
    with roster_errors(db):
        coached = coach_service.start(db, game)
        return coach_service.state(db, coached)


@router.post("/games/{game_id}/coach/call", response_model=CoachStateOut)
def make_call(request: CoachCallIn, game: Game = Depends(get_game),
              db: Session = Depends(get_db)):
    """Make the next call; the snap is played, up to the next call you need to make."""
    with roster_errors(db):
        return coach_service.call(db, coach_service.coached_game(db, game), request.play,
                                  request.package, request.timeout)


@router.post("/games/{game_id}/coach/auto", response_model=CoachStateOut)
def let_ai_call(request: CoachAutoIn, game: Game = Depends(get_game),
                db: Session = Depends(get_db)):
    """Let the AI call the next play, the rest of this drive, or the rest of the game."""
    with roster_errors(db):
        return coach_service.auto(db, coach_service.coached_game(db, game), request.scope)
