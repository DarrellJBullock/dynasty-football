from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.db import get_db
from app.models import Team
from app.schemas import (
    PlayerCreate,
    PlayerDetail,
    PlayerSummary,
    SigningRequest,
    TeamContracts,
    TeamDetail,
    TeamUpdate,
)
from app.services import contracts as contract_service
from app.services import leagues as league_service
from app.services import roster as roster_service
from app.services.serializers import player_detail, player_summary
from app.services.teams import load_overrides, load_roster, team_detail

router = APIRouter(prefix="/teams", tags=["teams"])


def get_team(team_id: int, db: Session = Depends(get_db)) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "team not found")
    return team


@router.get("/{team_id}", response_model=TeamDetail)
def read_team(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    return team_detail(team, load_roster(db, team.id), load_overrides(db, [team.id])[team.id])


@router.patch("/{team_id}", response_model=TeamDetail)
def update_team(payload: TeamUpdate, team: Team = Depends(get_team),
                db: Session = Depends(get_db)):
    """Edit a team's identity: city, nickname, abbreviation, colors, stadium."""
    with roster_errors(db):
        league_service.update_team(db, team, payload)
    return team_detail(team, load_roster(db, team.id), load_overrides(db, [team.id])[team.id])


@router.get("/{team_id}/roster", response_model=list[PlayerSummary])
def read_roster(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    return [player_summary(p) for p in load_roster(db, team.id)]


@router.post("/{team_id}/players", response_model=PlayerDetail, status_code=201)
def create_player(payload: PlayerCreate, team: Team = Depends(get_team),
                  db: Session = Depends(get_db)):
    with roster_errors(db):
        player = roster_service.create_player(db, team, payload)
    return player_detail(player)


@router.post("/{team_id}/signings", response_model=PlayerDetail)
def sign_player(request: SigningRequest, team: Team = Depends(get_team),
                db: Session = Depends(get_db)):
    with roster_errors(db):
        player = roster_service.sign_player(db, team, request)
    return player_detail(player)


@router.get("/{team_id}/contracts", response_model=TeamContracts)
def contracts(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Payroll now and next season, expiring deals with asking prices, all contracts."""
    return contract_service.contracts_view(db, team)
