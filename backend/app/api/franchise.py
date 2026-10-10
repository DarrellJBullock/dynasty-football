from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Franchise
from app.schemas import Dashboard, FranchiseOut
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
