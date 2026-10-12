from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import League, User
from app.schemas import TradeCenter, TradeEvaluation, TradeProposal, TradeResult
from app.services import trades as trade_service
from app.services.members import user_team_id

router = APIRouter(prefix="/leagues/{league_id}/trades", tags=["trades"])


@router.get("", response_model=TradeCenter)
def trade_center(partner_id: int | None = Query(None), league: League = Depends(get_league),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Both sides' players and picks with trade values, partners, the window, history."""
    center = trade_service.trade_center(db, league, partner_id,
                                       user_team_id(db, league.id, user))
    db.commit()  # next year's picks are created the first time they're needed
    return center


@router.post("/evaluate", response_model=TradeEvaluation)
def evaluate(proposal: TradeProposal, league: League = Depends(get_league),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    """How the other team would react, without making the trade."""
    with roster_errors(db):
        return trade_service.evaluate(db, league, proposal, user_team_id(db, league.id, user))


@router.post("", response_model=TradeResult)
def propose(proposal: TradeProposal, league: League = Depends(get_league),
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Propose a trade; it happens if the other team accepts."""
    with roster_errors(db):
        return trade_service.propose(db, league, proposal, user_team_id(db, league.id, user))
