from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.roster import RosterError


@contextmanager
def roster_errors(db: Session) -> Iterator[None]:
    """Run a roster mutation as one transaction; map rule violations to HTTP errors."""
    try:
        yield
        db.commit()
    except RosterError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.message) from exc
    except Exception:
        db.rollback()
        raise
