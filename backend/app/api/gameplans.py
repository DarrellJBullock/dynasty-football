from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.teams import get_team
from app.db import get_db
from app.models import Team
from app.schemas import GamePlanIn, GamePlanOut
from app.services import gameplans
from app.services.free_agency import franchise_team_id

router = APIRouter(prefix="/teams/{team_id}/game-plan", tags=["game plans"])


@router.get("", response_model=GamePlanOut)
def read_plan(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """The team's game plan (saved, or drawn from its roster), the plays and calls it can
    choose from, and what every plan must keep."""
    return gameplans.plan_view(db, team)


@router.put("", response_model=GamePlanOut)
def save_plan(payload: GamePlanIn, team: Team = Depends(get_team),
              db: Session = Depends(get_db)):
    """Save the franchise's game plan (422 with the reasons if it can't run)."""
    with roster_errors(db):
        gameplans.save(db, team, franchise_team_id(db, team.league_id), payload)
    return gameplans.plan_view(db, team)


@router.delete("", response_model=GamePlanOut)
def reset_plan(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Go back to the plan drawn from the roster."""
    with roster_errors(db):
        gameplans.reset(db, team, franchise_team_id(db, team.league_id))
    return gameplans.plan_view(db, team)
