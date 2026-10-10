from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.db import get_db
from app.models import Franchise
from app.schemas import Dashboard, FranchiseListItem, FranchiseOut
from app.services import leagues as league_service
from app.services.dashboard import build_dashboard, current_franchise, franchise_out

router = APIRouter(prefix="/franchise", tags=["franchise"])


def get_franchise(db: Session = Depends(get_db)) -> Franchise:
    franchise = current_franchise(db)
    if franchise is None:
        raise HTTPException(404, "no franchise found — run `make seed` to create the sample league")
    return franchise


@router.get("", response_model=FranchiseOut)
def read_franchise(franchise: Franchise = Depends(get_franchise), db: Session = Depends(get_db)):
    return franchise_out(db, franchise)


@router.get("/dashboard", response_model=Dashboard)
def dashboard(franchise: Franchise = Depends(get_franchise), db: Session = Depends(get_db)):
    return build_dashboard(db, franchise)


franchises_router = APIRouter(prefix="/franchises", tags=["franchise"])


@franchises_router.get("", response_model=list[FranchiseListItem])
def list_franchises(db: Session = Depends(get_db)):
    """All saved franchises, most recently active first."""
    return league_service.list_franchises(db)


@franchises_router.post("/{franchise_id}/activate", response_model=FranchiseOut)
def activate(franchise_id: int, db: Session = Depends(get_db)):
    franchise = db.get(Franchise, franchise_id)
    if franchise is None:
        raise HTTPException(404, "franchise not found")
    with roster_errors(db):
        league_service.activate_franchise(db, franchise)
    return franchise_out(db, franchise)
