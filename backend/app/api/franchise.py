from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.db import get_db
from app.models import Franchise, User
from app.schemas import Dashboard, FranchiseListItem, FranchiseOut
from app.services import leagues as league_service
from app.services.dashboard import build_dashboard, current_franchise, franchise_out

router = APIRouter(prefix="/franchise", tags=["franchise"])


NO_LEAGUE = "You don't have a league yet. Build one to get started."


def get_franchise(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Franchise:
    """The signed-in user's active franchise."""
    franchise = current_franchise(db, user)
    if franchise is None:
        raise HTTPException(404, NO_LEAGUE)
    return franchise


@router.get("", response_model=FranchiseOut)
def read_franchise(franchise: Franchise = Depends(get_franchise), db: Session = Depends(get_db)):
    return franchise_out(db, franchise)


@router.get("/dashboard", response_model=Dashboard)
def dashboard(franchise: Franchise = Depends(get_franchise), db: Session = Depends(get_db)):
    return build_dashboard(db, franchise)


franchises_router = APIRouter(prefix="/franchises", tags=["franchise"])


@franchises_router.get("", response_model=list[FranchiseListItem])
def list_franchises(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The user's saved franchises, most recently active first."""
    return league_service.list_franchises(db, user)


@franchises_router.post("/{franchise_id}/activate", response_model=FranchiseOut)
def activate(franchise_id: int, db: Session = Depends(get_db)):
    franchise = db.get(Franchise, franchise_id)
    if franchise is None:
        raise HTTPException(404, "franchise not found")
    with roster_errors(db):
        league_service.activate_franchise(db, franchise)
    return franchise_out(db, franchise)
