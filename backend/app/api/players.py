from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.db import get_db
from app.models import Player
from app.schemas import NegotiationResult, PlayerDetail, PlayerUpdate, ReSignOffer
from app.services import contracts as contract_service
from app.services import roster as roster_service
from app.services.serializers import player_detail

router = APIRouter(prefix="/players", tags=["players"])


def get_player(player_id: int, db: Session = Depends(get_db)) -> Player:
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(404, "player not found")
    return player


@router.get("/{player_id}", response_model=PlayerDetail)
def read_player(player: Player = Depends(get_player)):
    return player_detail(player)


@router.patch("/{player_id}", response_model=PlayerDetail)
def update_player(payload: PlayerUpdate, player: Player = Depends(get_player),
                  db: Session = Depends(get_db)):
    with roster_errors(db):
        roster_service.update_player(db, player, payload)
    return player_detail(player)


@router.post("/{player_id}/release", response_model=PlayerDetail)
def release_player(player: Player = Depends(get_player), db: Session = Depends(get_db)):
    with roster_errors(db):
        roster_service.release_player(db, player)
    return player_detail(player)


@router.post("/{player_id}/re-sign", response_model=NegotiationResult)
def re_sign(offer: ReSignOffer, player: Player = Depends(get_player),
            db: Session = Depends(get_db)):
    """Offer an expiring player a new deal (offseason only). A rejection isn't an error:
    the result says no and names his price."""
    with roster_errors(db):
        return contract_service.negotiate(db, player, offer)
