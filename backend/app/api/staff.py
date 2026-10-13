"""Staff: a team's coaches, scout and trainer, and the league's head coaches."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.leagues import get_league
from app.api.teams import get_team
from app.db import get_db
from app.models import League, Team
from app.schemas import CoachesOut, TeamStaffOut
from app.services import staff

router = APIRouter(tags=["staff"])


@router.get("/teams/{team_id}/staff", response_model=TeamStaffOut)
def team_staff(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """The team's head coach, coordinators, scout and trainer: ratings, contracts, careers."""
    view = staff.team_staff(db, team)
    db.commit()  # (a league from before staff gets one the first time it's asked)
    return view


@router.get("/leagues/{league_id}/coaches", response_model=CoachesOut)
def coaches(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Every team's head coach with his career, and Coach of the Year by season."""
    view = staff.coaches(db, league)
    db.commit()
    return view
