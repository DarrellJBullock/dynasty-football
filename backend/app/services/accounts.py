"""Accounts: sign up, sign in with server-side sessions, change password, delete.

Passwords are hashed with Argon2. A session is a random token in an HttpOnly cookie; the
database keeps only its SHA-256, and when it expires (30 days, extended as it's used).
"""

import hashlib
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import League, Notification, PasswordReset, User, UserSession
from app.services.errors import RosterError

SESSION_DAYS = 30
RESET_VALID = timedelta(hours=1)
EXTEND_AFTER = timedelta(days=1)  # extend a session's expiry at most once a day
MIN_PASSWORD, MAX_PASSWORD = 8, 128
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_hasher = PasswordHasher()


class AuthError(RosterError):
    """A sign-in or account rule failed (401 unless given a status)."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message, status_code)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _check_password(password: str) -> None:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise AuthError(f"Passwords are {MIN_PASSWORD} to {MAX_PASSWORD} characters.", 422)


def _verify(user: User, password: str) -> bool:
    try:
        return _hasher.verify(user.password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def sign_up(db: Session, email: str, password: str) -> User:
    """Create an account. The first account on an install takes over the leagues made
    before accounts existed, so a developer's saves carry over."""
    email = normalize_email(email)
    if not EMAIL.match(email) or len(email) > 254:
        raise AuthError("Enter a valid email address.", 422)
    _check_password(password)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AuthError("An account with that email already exists. Sign in instead.", 409)
    first = not db.scalar(select(func.count(User.id)))
    user = User(email=email, password_hash=_hasher.hash(password))
    db.add(user)
    db.flush()
    if first:
        from app.services.members import give_league  # (it builds on this module's users)

        for league in db.scalars(select(League).where(League.user_id.is_(None))).all():
            give_league(db, league, user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        _hasher.hash(password)  # take as long as a real check, so timing doesn't tell
        raise AuthError("Wrong email or password.")
    if not _verify(user, password):
        raise AuthError("Wrong email or password.")
    return user


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User) -> str:
    """A new session for the user; returns the token for the cookie."""
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.id, token_hash=_token_hash(token),
                       expires_at=_now() + timedelta(days=SESSION_DAYS)))
    db.flush()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    """The signed-in user for a session token, extending the session; None if it's
    unknown or expired."""
    session = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if session is None:
        return None
    now = _now()
    expires = _aware(session.expires_at)
    if expires <= now:
        db.delete(session)
        db.commit()
        return None
    if expires - now < timedelta(days=SESSION_DAYS) - EXTEND_AFTER:
        session.expires_at = now + timedelta(days=SESSION_DAYS)
        db.commit()
    return session.user


def end_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))


def change_password(db: Session, user: User, current: str, new: str, keep_token: str) -> None:
    """Change the password; every other session is signed out."""
    if not _verify(user, current):
        raise AuthError("Your current password is wrong.", 403)
    _check_password(new)
    user.password_hash = _hasher.hash(new)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id,
                                         UserSession.token_hash != _token_hash(keep_token)))


def request_reset(db: Session, email: str) -> tuple[User, str] | None:
    """A one-time password reset link's token for the account with this email (None if
    there's no such account; the caller answers the same either way)."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=_token_hash(token),
                         expires_at=_now() + RESET_VALID))
    db.flush()
    return user, token


def reset_password(db: Session, token: str, password: str) -> User:
    """Set a new password with a reset link's token: good once, within the hour. Signs
    the account out everywhere and spends its other links."""
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _token_hash(token)))
    if reset is None or reset.used_at is not None or _aware(reset.expires_at) <= _now():
        raise AuthError("This reset link has expired or was already used. Ask for a new one.",
                        400)
    _check_password(password)
    user = db.get(User, reset.user_id)
    user.password_hash = _hasher.hash(password)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id,
                                           PasswordReset.used_at.is_(None))
               .values(used_at=_now()))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    return user


def set_password(db: Session, email: str, password: str) -> User:
    """Admin reset (`python -m app.accounts`): set a password and sign out everywhere."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise AuthError(f"No account for {email}.", 404)
    _check_password(password)
    user.password_hash = _hasher.hash(password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    return user


def delete_account(db: Session, user: User, password: str) -> None:
    """Delete the account and every league in it."""
    from app.services.leagues import delete_league  # (they build on this module's users)
    from app.services.members import leave_all

    if not _verify(user, password):
        raise AuthError("Your password is wrong.", 403)
    for league in leave_all(db, user):  # (leagues shared with others carry on without them)
        delete_league(db, league)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.delete(user)
    db.flush()


def ensure_user(db: Session, email: str, password: str) -> User:
    """The account for `email`, created (or its password reset) as given: the local dev
    and e2e account that owns the seeded league."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        return sign_up(db, email, password)
    if not _verify(user, password):
        user.password_hash = _hasher.hash(password)
    return user


class RateLimiter:
    """Failed sign-ins per key (an email, an IP) in a sliding window. In-process: with
    several API instances each keeps its own count, which still caps guessing."""

    def __init__(self, limit: int = 10, window: float = 15 * 60):
        self.limit, self.window = limit, window
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str, now: float) -> deque[float]:
        times = self.failures[key]
        while times and now - times[0] > self.window:
            times.popleft()
        return times

    def blocked(self, *keys: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return any(len(self._recent(key, now)) >= self.limit for key in keys)

    def failed(self, *keys: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for key in keys:
            self._recent(key, now).append(now)

    def clear(self, *keys: str) -> None:
        for key in keys:
            self.failures.pop(key, None)
