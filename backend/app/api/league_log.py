"""The League log, and the commissioner's edits the roster editor doesn't make
(services/league_log.py)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.api.players import get_player
from app.db import get_db
from app.models import League, Player, User
from app.schemas import ContractEditIn, LeagueLogOut, PlayerDetail, PlayerMoveIn
from app.services import league_log
from app.services.serializers import player_detail

router = APIRouter(tags=["league log"])


def _money(amount: int | None) -> str:
    return "none" if amount is None else f"${amount / 1_000_000:.2f}M"


@router.get("/leagues/{league_id}/log", response_model=LeagueLogOut)
def read_log(league: League = Depends(get_league), before: int | None = None,
             action: str | None = Query(default=None, max_length=24),
             db: Session = Depends(get_db)):
    """Every edit and commissioner action, newest first (a page at a time)."""
    return league_log.entries(db, league.id, before, action)


@router.post("/players/{player_id}/move", response_model=PlayerDetail)
def move_player(body: PlayerMoveIn, player: Player = Depends(get_player),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The commissioner moves a player to another team (his contract goes with him) or to
    free agency."""
    with roster_errors(db):
        old, new = league_log.move_player(db, player, body.team_id)
        league_log.record(db, player.league_id, user, "move",
                          f"Moved {player.full_name} from {old} to {new}",
                          [{"field": "team", "before": old, "after": new}],
                          team_id=player.team_id, player_id=player.id)
    return player_detail(player)


@router.put("/players/{player_id}/contract", response_model=PlayerDetail)
def set_contract(body: ContractEditIn, player: Player = Depends(get_player),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The commissioner rewrites a player's contract."""
    with roster_errors(db):
        before, after = league_log.set_contract(db, player, body.salary, body.years)
        league_log.record(
            db, player.league_id, user, "contract",
            f"Changed {player.full_name}'s contract to {_money(after['salary'])} a season "
            f"through {after['end_year']}", league_log.diff(before, after),
            team_id=player.team_id, player_id=player.id)
    return player_detail(player)
