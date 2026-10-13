"""Staff: a team's coaches, scout and trainer, and the league's head coaches."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.leagues import get_league
from app.api.players import get_player
from app.api.teams import get_team
from app.db import get_db
from app.models import League, Player, Team
from app.schemas import CoachesOut, PlayerCoachingOut, TeamStaffOut
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


@router.get("/players/{player_id}/coaching", response_model=PlayerCoachingOut)
def player_coaching(player: Player = Depends(get_player), db: Session = Depends(get_db)):
    """What his team's coaches and trainer do for this player."""
    view = staff.player_coaching(db, player)
    db.commit()
    return view
