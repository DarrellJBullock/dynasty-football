"""Notifications (docs/design/leagues-with-friends.md §6): an inbox for each person, with a
count of unread items for the sidebar, and email for the kinds a member asks for (off by
default). Services call `notify` as things happen; email goes out from the worker's minute
(`send_pending`), never inside a request.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import League, LeagueMember, Notification, User
from app.schemas import NotificationOut, NotificationsOut
from app.services import email
from app.services.errors import RosterError

log = logging.getLogger("app.notifications")

KINDS = {  # kind: what the settings call it
    "your_pick": "You're on the clock in the draft",
    "trade_offer": "A trade offer for you",
    "trade_answer": "An answer to your trade offer",
    "trade_review": "A trade waiting for your veto (commissioners)",
    "advanced": "The league moved on",
    "game_result": "Your team's result",
    "waiting": "Everyone's waiting on you (or ready to go)",
    "member_joined": "Someone joined your league",
    "legacy": "The Hall of Fame class, and numbers to retire",
}
KEEP = 100  # notifications listed at a time


def _now() -> datetime:
    return datetime.now(UTC)


def notify(db: Session, user_id: int, kind: str, title: str, body: str = "",
           league_id: int | None = None, link: str | None = None,
           key: str | None = None) -> Notification | None:
    """Tell someone something. With a `key`, only once (later ones are dropped)."""
    assert kind in KINDS, kind
    if key and db.scalar(select(Notification.id).where(Notification.user_id == user_id,
                                                       Notification.key == key)):
        return None
    wants_email = False
    if league_id is not None:
        kinds = db.scalar(select(LeagueMember.email_kinds).where(
            LeagueMember.league_id == league_id, LeagueMember.user_id == user_id))
        wants_email = kind in (kinds or [])
    note = Notification(user_id=user_id, league_id=league_id, kind=kind, title=title[:120],
                        body=body[:300], link=link, key=key,
                        email="pending" if wants_email else None)
    db.add(note)
    db.flush()
    return note


def notify_members(db: Session, league_id: int, kind: str, title: str, body: str = "",
                   link: str | None = None, key: str | None = None,
                   skip: set[int] | None = None, role: str | None = None) -> None:
    """Tell every member of a league (but `skip`'s user ids; only `role`, if given)."""
    stmt = select(LeagueMember.user_id).where(LeagueMember.league_id == league_id)
    if role:
        stmt = stmt.where(LeagueMember.role == role)
    for user_id in db.scalars(stmt):
        if user_id not in (skip or set()):
            notify(db, user_id, kind, title, body, league_id, link, key)


def notify_team(db: Session, team_id: int, kind: str, title: str, body: str = "",
                link: str | None = None, key: str | None = None) -> None:
    """Tell whoever runs the team (nobody, if the AI does)."""
    from app.models import Franchise

    row = db.execute(select(Franchise.user_id, Franchise.league_id)
                     .where(Franchise.team_id == team_id)).first()
    if row and row.user_id:
        notify(db, row.user_id, kind, title, body, row.league_id, link, key)


# ---------- the inbox ----------

def _out(note: Notification, leagues: dict[int, str]) -> NotificationOut:
    return NotificationOut(id=note.id, kind=note.kind, title=note.title, body=note.body,
                           link=note.link, league=leagues.get(note.league_id),
                           created_at=note.created_at, read=note.read_at is not None)


def unread_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0


def inbox(db: Session, user: User) -> NotificationsOut:
    notes = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.id.desc()).limit(KEEP)).all()
    ids = {n.league_id for n in notes if n.league_id}
    leagues = dict(db.execute(select(League.id, League.name).where(League.id.in_(ids))).all())
    return NotificationsOut(unread=unread_count(db, user),
                            items=[_out(n, leagues) for n in notes])


def mark_read(db: Session, user: User, ids: list[int] | None) -> None:
    """Mark some of the user's notifications read (all of them, without ids)."""
    stmt = update(Notification).where(Notification.user_id == user.id,
                                      Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=_now()))
    db.flush()


def email_kinds(db: Session, league_id: int, user: User) -> list[str]:
    member = db.scalar(select(LeagueMember).where(LeagueMember.league_id == league_id,
                                                  LeagueMember.user_id == user.id))
    return [k for k in KINDS if k in (member.email_kinds or [])] if member else []


def set_email_kinds(db: Session, league_id: int, user: User, kinds: list[str]) -> list[str]:
    unknown = set(kinds) - set(KINDS)
    if unknown:
        raise RosterError(f"Unknown notifications: {', '.join(sorted(unknown))}.", 422)
    member = db.scalar(select(LeagueMember).where(LeagueMember.league_id == league_id,
                                                  LeagueMember.user_id == user.id))
    member.email_kinds = [k for k in KINDS if k in kinds]
    db.flush()
    return member.email_kinds


# ---------- email (the worker's minute) ----------

def send_pending(db: Session, limit: int = 50) -> int:
    """Email the notifications waiting for it. Returns how many went out. One that fails
    is marked so it isn't retried forever (the inbox still has it)."""
    sent = 0
    base = get_settings().site_url.rstrip("/")
    for note in db.scalars(select(Notification).where(Notification.email == "pending")
                           .order_by(Notification.id).limit(limit)).all():
        user = db.get(User, note.user_id)
        link = f"\n\n{base}{note.link}" if note.link else ""
        try:
            email.send(user.email, note.title, f"{note.body}{link}\n\n"
                       "You get these emails because you asked for them in your league's "
                       f"inbox settings: {base}/inbox")
        except Exception:  # noqa: BLE001 (the mail server: log it, keep the inbox item)
            log.exception("notification %s couldn't be emailed", note.id,
                          extra={"notification_id": note.id})
            note.email = "failed"
        else:
            note.email = "sent"
            sent += 1
        db.commit()
    return sent
