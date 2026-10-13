"""Staff: a team's coaches, scout and trainer, and the league's head coaches."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.api.players import get_player
from app.api.teams import get_team
from app.db import get_db
from app.models import League, Player, StaffMember, Team, User
from app.schemas import (
    CoachesOut,
    ExtendIn,
    HireIn,
    PlayerCoachingOut,
    StaffMarketOut,
    TeamStaffOut,
)
from app.services import carousel, facilities, staff
from app.services.members import user_team_id

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


# ---------- the coaching carousel (services/carousel.py) ----------


def get_staff(staff_id: int, db: Session = Depends(get_db)) -> StaffMember:
    member = db.get(StaffMember, staff_id)
    if member is None:
        raise HTTPException(404, "staff member not found")
    return member


@router.get("/leagues/{league_id}/staff-market", response_model=StaffMarketOut)
def market(league: League = Depends(get_league), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    """Staff out of work, with what they'd sign for, and your team's staff budget."""
    team_id = user_team_id(db, league.id, user)
    return carousel.market(db, league, db.get(Team, team_id) if team_id else None)


@router.post("/teams/{team_id}/staff/hire", response_model=TeamStaffOut)
def hire(body: HireIn, team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Hire someone off the market into an open job."""
    with roster_errors(db):
        carousel.hire(db, team, body.staff_id, body.years)
    return staff.team_staff(db, team)


@router.post("/staff/{staff_id}/fire", response_model=TeamStaffOut)
def fire(member: StaffMember = Depends(get_staff), db: Session = Depends(get_db)):
    """Let them go: what's left of their contract is owed as dead money."""
    team = db.get(Team, member.team_id) if member.team_id else None
    with roster_errors(db):
        carousel.fire(db, member)
    if team is None:
        raise HTTPException(409, "They aren't on a team.")
    return staff.team_staff(db, team)


@router.post("/staff/{staff_id}/extend", response_model=TeamStaffOut)
def extend(body: ExtendIn, member: StaffMember = Depends(get_staff),
           db: Session = Depends(get_db)):
    """Keep them on: a new contract from next season (in their contract's final season)."""
    with roster_errors(db):
        carousel.extend(db, member, body.years)
    return staff.team_staff(db, db.get(Team, member.team_id))


@router.post("/teams/{team_id}/facilities/{kind}/upgrade", response_model=TeamStaffOut)
def upgrade_facility(kind: str, team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Build a facility's next level: paid from this season's staff budget, ready next
    season."""
    with roster_errors(db):
        facilities.upgrade(db, team, kind)
    return staff.team_staff(db, team)
