from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.db import get_db
from app.models import Team, User
from app.schemas import (
    OwnerOut,
    PlayerCreate,
    PlayerDetail,
    PlayerSummary,
    SigningRequest,
    TeamContracts,
    TeamDetail,
    TeamUpdate,
)
from app.services import contracts as contract_service
from app.services import draft as draft_service
from app.services import league_log, owners
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
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Edit a team's identity: city, nickname, abbreviation, colors, stadium (in the League
    log)."""
    before = league_log.team_fields(team)
    with roster_errors(db):
        league_service.update_team(db, team, payload)
        changes = league_log.diff(before, league_log.team_fields(team))
        if changes:
            league_log.record(db, team.league_id, user, "team", f"Edited the {team.full_name}",
                              changes, team_id=team.id)
    return team_detail(team, load_roster(db, team.id), load_overrides(db, [team.id])[team.id])


@router.get("/{team_id}/owner", response_model=OwnerOut)
def read_owner(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """The team's owner and fans: what the owner wants, this season's goals and how they're
    going, confidence and fan mood (and what moved them), and the last review."""
    view = owners.owner_view(db, team)
    db.commit()  # (a league from before owners gets them the first time they're asked)
    return view


@router.get("/{team_id}/roster", response_model=list[PlayerSummary])
def read_roster(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    return [player_summary(p) for p in load_roster(db, team.id)]


@router.post("/{team_id}/players", response_model=PlayerDetail, status_code=201)
def create_player(payload: PlayerCreate, team: Team = Depends(get_team),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    with roster_errors(db):
        player = roster_service.create_player(db, team, payload)
        league_log.record(db, team.league_id, user, "new_player",
                          f"Added {player.position} {player.full_name} ({player.overall}) "
                          f"to the {team.full_name}", team_id=team.id, player_id=player.id)
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


@router.post("/{team_id}/cut-down", response_model=list[PlayerSummary])
def cut_down(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Release the lowest-rated players until the roster is at the 53-man limit."""
    with roster_errors(db):
        released = draft_service.cut_down(db, team)
    return [player_summary(p) for p in released]
