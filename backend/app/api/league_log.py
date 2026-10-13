"""The League log, and the commissioner's edits the roster editor doesn't make
(services/league_log.py)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.api.players import get_player
from app.db import get_db
from app.models import League, Player, Trade, User
from app.schemas import (
    ContractEditIn,
    LeagueLogOut,
    PlayerDetail,
    PlayerMoveIn,
    RollbackOut,
    SeasonTradeOut,
)
from app.services import league_log, rollback
from app.services import trades as trade_service
from app.services.notifications import notify_members, notify_team
from app.services.serializers import player_detail
from app.services.teams import current_season

router = APIRouter(tags=["league log"])


def get_trade(trade_id: int, db: Session = Depends(get_db)) -> Trade:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(404, "trade not found")
    return trade


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


@router.post("/trades/{trade_id}/reverse", response_model=SeasonTradeOut)
def reverse_trade(trade: Trade = Depends(get_trade), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """The commissioner undoes a trade from this season: everything goes back (refused,
    with why, once anyone in it has moved on)."""
    with roster_errors(db):
        trade_service.reverse(db, trade)
        summary = (f"Reversed the trade between the {trade.team.full_name} and the "
                   f"{trade.partner.full_name}")
        items = ", ".join(i["label"] for i in [*trade.sent, *trade.received])
        league_log.record(db, trade.league_id, user, "reverse", f"{summary} ({items})",
                          team_id=trade.team_id)
        for team_id in (trade.team_id, trade.partner_id):
            notify_team(db, team_id, "trade_answer", "The commissioner reversed a trade",
                        f"{summary}: everyone in it went back.", "/trades",
                        key=f"reversed:{trade.id}")
    return trade_service.season_trade_out(db, trade)


@router.get("/leagues/{league_id}/rollback", response_model=RollbackOut)
def read_rollback(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """The week (or playoff round) the commissioner can roll back, if any."""
    shot = rollback.latest(db, current_season(db, league.id))
    return RollbackOut(label=shot.label if shot else None)


@router.post("/leagues/{league_id}/rollback", response_model=RollbackOut)
def roll_back(league: League = Depends(get_league), user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    """The commissioner rolls back the last week (or playoff round): its games, box scores,
    injuries, awards and notifications go; rosters stay as they are."""
    with roster_errors(db):
        label = rollback.roll_back(db, league.id)
        league_log.record(db, league.id, user, "rollback", f"Rolled back {label}")
        notify_members(db, league.id, "advanced", f"{league.name}: {label} was rolled back",
                       f"The commissioner undid {label}: it will be played again.", "/",
                       skip={user.id})
    return RollbackOut(label=label)
