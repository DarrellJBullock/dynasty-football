"""Who may do what: the signed-in user (from the session cookie), the league a route's
path ids belong to, and the checks every router runs:

- `current_user`: 401 without a valid session.
- `owned_league`: 404 for anything in a league the user isn't a member of, so ids don't
  reveal what exists. Every resource reaches a league through its path ids (`league_of`).
- `allowed`: who may change what (403 otherwise), from `WRITES`, which names a rule for
  every change route (docs/design/leagues-with-friends.md §3): commissioners run the
  league, managers their own team.
- `same_site`: a browser's change from another site is refused (403); with
  `SameSite=Lax` cookies this stops cross-site request forgery.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import (
    Franchise,
    Game,
    Job,
    League,
    Player,
    Season,
    StaffMember,
    Team,
    TradeOffer,
    User,
)
from app.services import accounts, members

SESSION_COOKIE = "df_session"
READS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = accounts.user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    request.state.user_id = user.id  # (for the request's log line)
    return user


def league_of(db: Session, params: dict[str, str]) -> int | None:
    """The league a route's path parameters belong to, if they name one that exists."""
    if "league_id" in params:
        return int(params["league_id"])
    models = {"season_id": Season, "team_id": Team, "player_id": Player,
              "franchise_id": Franchise, "job_id": Job, "offer_id": TradeOffer,
              "staff_id": StaffMember}
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
    if db.get(League, league_id) is None:
        return None  # (the route itself answers 404)
    if members.member(db, league_id, user) is None:
        raise HTTPException(404, "Not found.")
    return league_id


# Who may make each change ("METHOD path"):
# - commissioner: a commissioner of the league.
# - team: the path's team (or player's team) is the user's, or they're a commissioner.
#   A player without a team: a commissioner (`free_agent` names the exceptions).
# - free_agent: as `team`, but for a free agent or prospect, any member who runs a team
#   (offers, scouting).
# - game: the user runs a team in the game, or is a commissioner and a member's team
#   plays in it.
# - has_team: any member who runs a team (the service acts for that team).
# - staff: the staff member's team is the user's, or they're a commissioner.
# - member: any member.
# - own_franchise: the franchise is the user's.
WRITES = {
    "DELETE /api/leagues/{league_id}": "commissioner",
    "PATCH /api/teams/{team_id}": "team",
    "POST /api/teams/{team_id}/players": "team",
    "POST /api/teams/{team_id}/signings": "team",
    "POST /api/teams/{team_id}/cut-down": "team",
    "DELETE /api/teams/{team_id}/depth-chart": "team",
    "PUT /api/teams/{team_id}/depth-chart/{slot}": "team",
    "DELETE /api/teams/{team_id}/depth-chart/{slot}": "team",
    "PUT /api/teams/{team_id}/game-plan": "team",
    "DELETE /api/teams/{team_id}/game-plan": "team",
    "POST /api/teams/{team_id}/roster-import/preview": "team",
    "POST /api/teams/{team_id}/roster-import/commit": "team",
    "PATCH /api/players/{player_id}": "team",
    "POST /api/players/{player_id}/release": "team",
    "POST /api/players/{player_id}/re-sign": "team",
    "POST /api/players/{player_id}/offer": "free_agent",
    "DELETE /api/players/{player_id}/offer": "free_agent",
    "POST /api/players/{player_id}/scout": "free_agent",
    "POST /api/seasons/{season_id}/simulate": "commissioner",
    "POST /api/seasons/{season_id}/advance": "commissioner",
    "POST /api/seasons/{season_id}/free-agency": "commissioner",
    "POST /api/seasons/{season_id}/draft": "commissioner",
    "POST /api/leagues/{league_id}/jobs": "commissioner",
    "DELETE /api/jobs/{job_id}": "commissioner",
    "POST /api/leagues/{league_id}/draft/pick": "has_team",
    "POST /api/leagues/{league_id}/trades": "has_team",
    "POST /api/leagues/{league_id}/trades/evaluate": "has_team",
    "POST /api/games/{game_id}/coach": "game",
    "DELETE /api/games/{game_id}/coach": "game",
    "POST /api/games/{game_id}/coach/call": "game",
    "POST /api/games/{game_id}/coach/auto": "game",
    "POST /api/franchises/{franchise_id}/activate": "own_franchise",
    "POST /api/leagues/{league_id}/invites": "commissioner",
    "PUT /api/leagues/{league_id}/ready": "has_team",
    "POST /api/leagues/{league_id}/trade-offers": "has_team",
    "POST /api/trade-offers/{offer_id}/accept": "has_team",  # (the service checks which side)
    "POST /api/trade-offers/{offer_id}/reject": "has_team",
    "POST /api/trade-offers/{offer_id}/counter": "has_team",
    "POST /api/trade-offers/{offer_id}/withdraw": "has_team",
    "POST /api/trade-offers/{offer_id}/veto": "commissioner",
    "POST /api/trade-offers/{offer_id}/approve": "commissioner",
    "POST /api/leagues/{league_id}/advance": "commissioner",
    "PATCH /api/leagues/{league_id}/settings": "commissioner",
    "PUT /api/leagues/{league_id}/notification-settings": "member",
    "POST /api/leagues/{league_id}/share": "commissioner",
    "DELETE /api/leagues/{league_id}/share": "commissioner",
    "POST /api/teams/{team_id}/retired-numbers": "team",
    "POST /api/teams/{team_id}/staff/hire": "team",
    "POST /api/staff/{staff_id}/fire": "staff",
    "POST /api/staff/{staff_id}/extend": "staff",
    "DELETE /api/leagues/{league_id}/invites/{invite_id}": "commissioner",
    "PATCH /api/leagues/{league_id}/members/{member_id}": "commissioner",
    "DELETE /api/leagues/{league_id}/members/{member_id}": "member",  # (leave, or remove)
}
NO_TEAM = "You don't run a team in this league."


def allowed(request: Request, league_id: int | None = Depends(owned_league),
            user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    """Router dependency: the user may make this change (403 otherwise). Reads are open to
    every member; a route the user may not change says why."""
    if request.method in READS or league_id is None:
        return
    route = request.scope.get("route")
    path = getattr(route, "path", "")  # (inside the /api router: without its prefix)
    rule = WRITES.get(f"{request.method} {path}") or WRITES.get(f"{request.method} /api{path}")
    if rule is None:  # (a route without a league id: it scopes itself to the user)
        return
    if not _passes(db, rule, request.path_params, league_id, user):
        raise HTTPException(403, NO_TEAM if rule == "has_team" else
                            "Only a commissioner or the team's manager can do that.")


def _passes(db: Session, rule: str, params: dict[str, str], league_id: int,
            user: User) -> bool:
    commissioner = members.is_commissioner(db, league_id, user)
    mine = members.user_team_id(db, league_id, user)
    if rule == "commissioner":
        return commissioner
    if rule in ("team", "free_agent"):
        if "team_id" in params:
            team_id = int(params["team_id"])
        else:
            team_id = db.get(Player, int(params["player_id"])).team_id
            if team_id is None:
                return mine is not None if rule == "free_agent" else commissioner
        return commissioner or team_id == mine
    if rule == "game":
        game = db.get(Game, int(params["game_id"]))
        playing = {game.home_team_id, game.away_team_id}
        return mine in playing or (commissioner and bool(
            members.human_team_ids(db, league_id) & playing))
    if rule == "has_team":
        return mine is not None
    if rule == "staff":
        member = db.get(StaffMember, int(params["staff_id"]))
        return commissioner or (member.team_id is not None and member.team_id == mine)
    if rule == "own_franchise":
        return db.get(Franchise, int(params["franchise_id"])).user_id == user.id
    return rule == "member"


def same_site(request: Request) -> None:
    """Router dependency: refuse a browser's change sent from another site. Requests
    without an Origin header (scripts, tests) aren't from a browser page."""
    origin = request.headers.get("origin")
    if request.method not in READS and origin and origin not in get_settings().allowed_origins:
        raise HTTPException(403, "Cross-site request refused.")
