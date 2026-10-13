"""The inbox: the signed-in user's notifications, and which kinds they also get by email."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import League, User
from app.schemas import (
    MarkReadIn,
    NotificationKind,
    NotificationSettingsIn,
    NotificationSettingsOut,
    NotificationsOut,
    UnreadOut,
)
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationsOut)
def inbox(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Your latest notifications, newest first, and how many are unread."""
    return notifications.inbox(db, user)


@router.get("/notifications/unread", response_model=UnreadOut)
def unread(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """How many are unread (the sidebar's badge polls this)."""
    return UnreadOut(unread=notifications.unread_count(db, user))


@router.post("/notifications/read", response_model=UnreadOut)
def mark_read(body: MarkReadIn, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    """Mark notifications read (all of them, without ids)."""
    notifications.mark_read(db, user, body.ids)
    db.commit()
    return UnreadOut(unread=notifications.unread_count(db, user))


def _settings(kinds: list[str]) -> NotificationSettingsOut:
    return NotificationSettingsOut(kinds=[
        NotificationKind(kind=k, label=label, email=k in kinds)
        for k, label in notifications.KINDS.items()])


@router.get("/leagues/{league_id}/notification-settings", response_model=NotificationSettingsOut)
def settings(league: League = Depends(get_league), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Which kinds of notification from this league also come by email (none, at first)."""
    return _settings(notifications.email_kinds(db, league.id, user))


@router.put("/leagues/{league_id}/notification-settings", response_model=NotificationSettingsOut)
def update_settings(body: NotificationSettingsIn, league: League = Depends(get_league),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    with roster_errors(db):
        kinds = notifications.set_email_kinds(db, league.id, user, body.email)
    return _settings(kinds)
