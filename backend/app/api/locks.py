"""The league lock: while a background job is queued or running in a league, the league's
other changes are refused (409), so nothing changes under a simulation. Reads still work."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Franchise, Game, Player, Season, Team
from app.services.season import active_job

READS = {"GET", "HEAD", "OPTIONS"}


def league_of(db: Session, params: dict[str, str]) -> int | None:
    """The league a route's path parameters belong to, if they name one."""
    if "league_id" in params:
        return int(params["league_id"])
    models = {"season_id": Season, "team_id": Team, "player_id": Player,
              "franchise_id": Franchise}
    for key, model in models.items():
        if key in params:
            row = db.get(model, int(params[key]))
            return row.league_id if row else None
    if "game_id" in params:
        game = db.get(Game, int(params["game_id"]))
        return game.season.league_id if game else None
    return None


def league_unlocked(request: Request, db: Session = Depends(get_db)) -> None:
    """Router dependency: refuse changes to a league with a background job in progress."""
    if request.method in READS:
        return
    try:
        league_id = league_of(db, request.path_params)
    except ValueError:  # a malformed id: the route's own validation answers
        return
    if league_id is not None and active_job(db, league_id) is not None:
        raise HTTPException(409, "A simulation is running in this league. "
                                 "Wait for it to finish, or cancel it.")
