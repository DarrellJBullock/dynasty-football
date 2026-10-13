"""Legacy: the Hall of Fame, retired numbers, and each team's record book."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.api.teams import get_team
from app.db import get_db
from app.models import League, Team, User
from app.schemas import HallOfFameOut, RetireNumberIn, TeamRecordsOut
from app.services import legacy
from app.services.members import can_run_team

router = APIRouter(tags=["legacy"])


@router.get("/leagues/{league_id}/hall-of-fame", response_model=HallOfFameOut)
def hall_of_fame(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Every member of the Hall of Fame, the latest ballot's near misses, and the league's
    retired numbers."""
    return legacy.hall_of_fame(db, league)


@router.get("/teams/{team_id}/records", response_model=TeamRecordsOut)
def records(team: Team = Depends(get_team), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """The team's record book (games for this team), its Hall of Famers and retired
    numbers, and, for whoever runs it, former players whose numbers it could retire."""
    return legacy.team_records(db, team, can_run_team(db, team, user))


@router.post("/teams/{team_id}/retired-numbers", response_model=TeamRecordsOut,
             status_code=201)
def retire_number(body: RetireNumberIn, team: Team = Depends(get_team),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Retire a former player's number: the team never issues it again."""
    with roster_errors(db):
        legacy.retire_number(db, team, body.player_id)
    return legacy.team_records(db, team, can_run_team(db, team, user))
