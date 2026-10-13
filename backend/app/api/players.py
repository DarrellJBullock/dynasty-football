from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.db import get_db
from app.models import Player, User
from app.schemas import (
    ContractTerms,
    NegotiationResult,
    PlayerDetail,
    PlayerUpdate,
    ProspectRow,
    ReSignOffer,
)
from app.services import contracts as contract_service
from app.services import draft as draft_service
from app.services import free_agency as free_agency_service
from app.services import league_log
from app.services import roster as roster_service
from app.services.members import is_commissioner, user_team_id
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


# What a manager may change about their own players (the rest is the commissioner's).
MANAGER_EDITS = {"jersey_number"}


@router.patch("/{player_id}", response_model=PlayerDetail)
def update_player(payload: PlayerUpdate, player: Player = Depends(get_player),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edit a player (the commissioner; a manager only changes a jersey number). The edit
    goes in the League log."""
    if (payload.model_fields_set - MANAGER_EDITS
            and not is_commissioner(db, player.league_id, user)):
        raise HTTPException(403, "Only a commissioner can edit a player's ratings or bio.")
    before = league_log.player_fields(player)
    with roster_errors(db):
        roster_service.update_player(db, player, payload)
        changes = league_log.diff(before, league_log.player_fields(player))
        if changes:
            league_log.record(db, player.league_id, user, "player",
                              f"Edited {player.full_name}", changes,
                              team_id=player.team_id, player_id=player.id)
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


@router.post("/{player_id}/offer", status_code=204)
def make_offer(offer: ReSignOffer, player: Player = Depends(get_player),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """During free agency: offer this free agent a deal (replaces any earlier offer). He
    decides when the market day is played."""
    with roster_errors(db):
        free_agency_service.make_offer(db, player, ContractTerms(**offer.model_dump()),
                                       user_team_id(db, player.league_id, user))


@router.delete("/{player_id}/offer", status_code=204)
def withdraw_offer(player: Player = Depends(get_player), user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    with roster_errors(db):
        free_agency_service.withdraw_offer(db, player, user_team_id(db, player.league_id, user))


@router.post("/{player_id}/scout", response_model=ProspectRow)
def scout(player: Player = Depends(get_player), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    """Spend a scouting report on a draft prospect: reveals his true OVR and potential."""
    with roster_errors(db):
        return draft_service.scout(db, player, user_team_id(db, player.league_id, user))
