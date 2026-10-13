from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import League, Team, TradeOffer, User
from app.schemas import (
    TradeCenter,
    TradeEvaluation,
    TradeOfferIn,
    TradeOfferOut,
    TradeProposal,
    TradeResult,
    VetoIn,
)
from app.services import league_log, trade_offers
from app.services import trades as trade_service
from app.services.members import is_commissioner, user_team_id

router = APIRouter(prefix="/leagues/{league_id}/trades", tags=["trades"])


@router.get("", response_model=TradeCenter)
def trade_center(partner_id: int | None = Query(None), league: League = Depends(get_league),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Both sides' players and picks with trade values, partners, the window, history."""
    center = trade_service.trade_center(db, league, partner_id,
                                       user_team_id(db, league.id, user),
                                       is_commissioner(db, league.id, user))
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


# ---------- offers between managers (services/trade_offers.py) ----------

offers_router = APIRouter(tags=["trades"])


def get_offer(offer_id: int, db: Session = Depends(get_db)) -> TradeOffer:
    offer = db.get(TradeOffer, offer_id)
    if offer is None:
        raise HTTPException(404, "offer not found")
    return offer


def _mine(db: Session, offer: TradeOffer, user: User) -> int | None:
    return user_team_id(db, offer.league_id, user)


@offers_router.post("/leagues/{league_id}/trade-offers", response_model=TradeOfferOut,
                    status_code=201)
def make_offer(body: TradeOfferIn, league: League = Depends(get_league),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Offer a trade to another member's team; its manager accepts, rejects or counters."""
    team_id = user_team_id(db, league.id, user)
    with roster_errors(db):
        offer = trade_offers.make(db, league, team_id, body.proposal, body.note)
    return trade_offers.offer_out(db, offer, team_id)


def _answer(action, offer: TradeOffer, user: User, db: Session) -> TradeOfferOut:
    team_id = _mine(db, offer, user)
    with roster_errors(db):
        result = action(db, offer, team_id)
    return trade_offers.offer_out(db, result, team_id)


@offers_router.post("/trade-offers/{offer_id}/accept", response_model=TradeOfferOut)
def accept(offer: TradeOffer = Depends(get_offer), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    """Accept: the trade goes through (after the commissioner's veto window, if any)."""
    return _answer(trade_offers.accept, offer, user, db)


@offers_router.post("/trade-offers/{offer_id}/reject", response_model=TradeOfferOut)
def reject(offer: TradeOffer = Depends(get_offer), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    return _answer(trade_offers.reject, offer, user, db)


@offers_router.post("/trade-offers/{offer_id}/withdraw", response_model=TradeOfferOut)
def withdraw(offer: TradeOffer = Depends(get_offer), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    return _answer(trade_offers.withdraw, offer, user, db)


@offers_router.post("/trade-offers/{offer_id}/counter", response_model=TradeOfferOut,
                    status_code=201)
def counter(body: TradeOfferIn, offer: TradeOffer = Depends(get_offer),
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Answer with another offer, back to the team that made this one."""
    return _answer(lambda d, o, t: trade_offers.counter(d, o, t, body.proposal, body.note),
                   offer, user, db)


@offers_router.post("/trade-offers/{offer_id}/veto", response_model=TradeOfferOut)
def veto(body: VetoIn, offer: TradeOffer = Depends(get_offer),
         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The commissioner stops an accepted trade during the veto window."""
    out = _answer(lambda d, o, _t: trade_offers.veto(d, o, body.reason), offer, user, db)
    _log(db, offer, user, "veto", f"Vetoed the trade between {_teams(db, offer)}: {offer.reason}")
    return out


@offers_router.post("/trade-offers/{offer_id}/approve", response_model=TradeOfferOut)
def approve(offer: TradeOffer = Depends(get_offer), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """The commissioner lets an accepted trade through now."""
    out = _answer(lambda d, o, _t: trade_offers.approve(d, o), offer, user, db)
    _log(db, offer, user, "approve", f"Let the trade between {_teams(db, offer)} through")
    return out


def _teams(db: Session, offer: TradeOffer) -> str:
    return " and the ".join(
        "the " * (i == 0) + db.get(Team, t).full_name
        for i, t in enumerate((offer.from_team_id, offer.to_team_id)))


def _log(db: Session, offer: TradeOffer, user: User, action: str, summary: str) -> None:
    league_log.record(db, offer.league_id, user, action, summary, team_id=offer.from_team_id)
    db.commit()
