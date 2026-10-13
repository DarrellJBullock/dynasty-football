"""Playing head-to-head: a live game between two members' teams (services/live.py)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.db import get_db
from app.models import Game, User
from app.schemas import CoachAutoIn, CoachCallIn, LiveOfferIn, LiveStateOut
from app.services import live
from app.services.members import user_team_id

router = APIRouter(prefix="/games/{game_id}/live", tags=["live games"])


def get_game(game_id: int, db: Session = Depends(get_db)) -> Game:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "game not found")
    return game


def _mine(db: Session, game: Game, user: User) -> int | None:
    return user_team_id(db, game.season.league_id, user)


def _view(db: Session, game: Game, user: User, before: int | None = None) -> LiveStateOut:
    found = live.live_game(db, game)
    if found is None:
        raise HTTPException(404, "Nobody has offered to play this game live.")
    view = live.state(db, found, _mine(db, game, user), before=before)
    db.commit()  # (a call clock that ran out, or the final whistle, is settled first)
    return view


@router.get("", response_model=LiveStateOut)
def read(game: Game = Depends(get_game), user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """The live game as you see it: your call to make, or who it waits on, and the plays."""
    return _view(db, game, user)


@router.post("", response_model=LiveStateOut, status_code=201)
def offer(body: LiveOfferIn, game: Game = Depends(get_game), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    """Offer to play this week's game against the other manager live."""
    with roster_errors(db):
        live.offer(db, game, _mine(db, game, user), body.clock_seconds)
    return _view(db, game, user)


@router.post("/accept", response_model=LiveStateOut)
def accept(game: Game = Depends(get_game), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    with roster_errors(db):
        live.accept(db, game, _mine(db, game, user))
    return _view(db, game, user)


@router.post("/decline", response_model=LiveStateOut)
def decline(game: Game = Depends(get_game), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    with roster_errors(db):
        live.decline(db, game, _mine(db, game, user))
    return _view(db, game, user)


def _side(db: Session, game: Game, user: User) -> str:
    side = live.side_of(game, _mine(db, game, user))
    if side is None:
        raise HTTPException(403, "Only the two teams' managers coach this game.")
    return side


@router.post("/call", response_model=LiveStateOut)
def call(body: CoachCallIn, game: Game = Depends(get_game), user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """Your call for the snap the game waits on (it plays once both coaches have called)."""
    side = _side(db, game, user)
    found = live.live_game(db, game)
    if found is None:
        raise HTTPException(404, "Nobody has offered to play this game live.")
    before = len(live.live_plays(found))
    with roster_errors(db):
        live.call(db, found, side, body.play, body.package, body.timeout)
    return _view(db, game, user, before)


@router.post("/auto", response_model=LiveStateOut)
def auto(body: CoachAutoIn, game: Game = Depends(get_game), user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """Let the AI call for you: the next call, the rest of this drive, or the game."""
    side = _side(db, game, user)
    found = live.live_game(db, game)
    if found is None:
        raise HTTPException(404, "Nobody has offered to play this game live.")
    before = len(live.live_plays(found))
    with roster_errors(db):
        live.auto(db, found, side, body.scope)
    return _view(db, game, user, before)
