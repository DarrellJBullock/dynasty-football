from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.teams import get_team
from app.db import get_db
from app.domain.positions import Position
from app.models import Team
from app.schemas import DepthChart, DepthSlotUpdate
from app.services import depth_chart as depth_chart_service

router = APIRouter(prefix="/teams/{team_id}/depth-chart", tags=["depth chart"])


@router.get("", response_model=DepthChart)
def read_depth_chart(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    return depth_chart_service.read_depth_chart(db, team)


@router.put("/{slot}", response_model=DepthChart)
def set_slot(slot: Position, payload: DepthSlotUpdate, team: Team = Depends(get_team),
             db: Session = Depends(get_db)):
    with roster_errors(db):
        depth_chart_service.set_slot(db, team, slot, payload.player_ids)
    return depth_chart_service.read_depth_chart(db, team)


@router.delete("/{slot}", response_model=DepthChart)
def reset_slot(slot: Position, team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Return one slot to automatic (OVR) ordering."""
    with roster_errors(db):
        depth_chart_service.reset_slot(db, team, slot)
    return depth_chart_service.read_depth_chart(db, team)


@router.delete("", response_model=DepthChart)
def reset_all(team: Team = Depends(get_team), db: Session = Depends(get_db)):
    """Return every slot to automatic (OVR) ordering."""
    with roster_errors(db):
        depth_chart_service.reset_all(db, team)
    return depth_chart_service.read_depth_chart(db, team)
