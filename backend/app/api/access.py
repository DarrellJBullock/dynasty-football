"""Who may do what: the signed-in user (from the session cookie), the league a route's
path ids belong to, and the checks every router runs:

- `current_user`: 401 without a valid session.
- `owned_league`: 404 for anything in someone else's league, so ids don't reveal what
  exists. Every resource reaches a league through its path ids (`league_of`).
- `same_site`: a browser's change from another site is refused (403); with
  `SameSite=Lax` cookies this stops cross-site request forgery.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Franchise, Game, Job, League, Player, Season, Team, User
from app.services import accounts

SESSION_COOKIE = "df_session"
READS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = accounts.user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user


def league_of(db: Session, params: dict[str, str]) -> int | None:
    """The league a route's path parameters belong to, if they name one that exists."""
    if "league_id" in params:
        return int(params["league_id"])
    models = {"season_id": Season, "team_id": Team, "player_id": Player,
              "franchise_id": Franchise, "job_id": Job}
    for key, model in models.items():
        if key in params:
            row = db.get(model, int(params[key]))
            return row.league_id if row else None
    if "game_id" in params:
        game = db.get(Game, int(params["game_id"]))
        return game.season.league_id if game else None
    return None


def owned_league(request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> int | None:
    """Router dependency: the route's league must be the user's (404 otherwise). Returns
    its id, or None for routes that don't name one (and for ids that don't exist, which
    the route itself answers with a 404)."""
    try:
        league_id = league_of(db, request.path_params)
    except ValueError:  # a malformed id: the route's own validation answers
        return None
    if league_id is None:
        return None
    league = db.get(League, league_id)
    if league is not None and league.user_id != user.id:
        raise HTTPException(404, "Not found.")
    return league_id


def same_site(request: Request) -> None:
    """Router dependency: refuse a browser's change sent from another site. Requests
    without an Origin header (scripts, tests) aren't from a browser page."""
    origin = request.headers.get("origin")
    if request.method not in READS and origin and origin not in get_settings().allowed_origins:
        raise HTTPException(403, "Cross-site request refused.")
