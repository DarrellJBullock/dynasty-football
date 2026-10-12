"""The league lock: while a background job is queued or running in a league, the league's
other changes are refused (409), so nothing changes under a simulation. Reads still work."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.access import READS, owned_league
from app.db import get_db
from app.services.season import active_job


def league_unlocked(request: Request, league_id: int | None = Depends(owned_league),
                    db: Session = Depends(get_db)) -> None:
    """Router dependency: refuse changes to a league with a background job in progress."""
    if request.method in READS or league_id is None:
        return
    if active_job(db, league_id) is not None:
        raise HTTPException(409, "A simulation is running in this league. "
                                 "Wait for it to finish, or cancel it.")
