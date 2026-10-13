from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import SESSION_COOKIE, current_user
from app.api.errors import roster_errors
from app.config import get_settings
from app.db import get_db
from app.models import LeagueMember, User
from app.schemas import (
    AccountDeletion,
    Credentials,
    PasswordChange,
    PasswordResetIn,
    ProfileIn,
    ResetRequest,
    UserOut,
)
from app.services import accounts, email
from app.services.members import display_name

router = APIRouter(prefix="/auth", tags=["accounts"])

# Failed sign-ins: 10 per email and 50 per address in 15 minutes.
by_email = accounts.RateLimiter(limit=10)
by_address = accounts.RateLimiter(limit=50)
# Reset emails: 5 per email address an hour.
resets = accounts.RateLimiter(limit=5, window=3600)


def user_out(db: Session, user: User) -> UserOut:
    has_league = db.scalar(select(LeagueMember.id).where(LeagueMember.user_id == user.id)
                           .limit(1))
    return UserOut(id=user.id, email=user.email, display_name=display_name(user),
                   has_league=has_league is not None)


def _address(request: Request) -> str:
    """The browser's address. The API sits behind the web app's proxy, which passes it
    on in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sign_in(db: Session, response: Response, user: User) -> None:
    token = accounts.start_session(db, user)
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=accounts.SESSION_DAYS * 24 * 3600,
                        httponly=True, samesite="lax", secure=get_settings().cookie_secure,
                        path="/")


@router.post("/signup", response_model=UserOut, status_code=201)
def sign_up(credentials: Credentials, response: Response, db: Session = Depends(get_db)):
    """Create an account and sign in. The first account on an install takes over the
    leagues made before accounts."""
    with roster_errors(db):
        user = accounts.sign_up(db, credentials.email, credentials.password)
    _sign_in(db, response, user)
    return user_out(db, user)


@router.post("/signin", response_model=UserOut)
def sign_in(credentials: Credentials, request: Request, response: Response,
            db: Session = Depends(get_db)):
    """Sign in: sets the session cookie. Repeated failures are refused for a while (429)."""
    keys = (f"email:{accounts.normalize_email(credentials.email)}", f"ip:{_address(request)}")
    if by_email.blocked(keys[0]) or by_address.blocked(keys[1]):
        raise HTTPException(429, "Too many failed sign-ins. Try again in a few minutes.")
    try:
        user = accounts.authenticate(db, credentials.email, credentials.password)
    except accounts.AuthError as exc:
        by_email.failed(keys[0])
        by_address.failed(keys[1])
        raise HTTPException(exc.status_code, exc.message) from exc
    by_email.clear(keys[0])
    _sign_in(db, response, user)
    return user_out(db, user)


@router.post("/signout", status_code=204)
def sign_out(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        accounts.end_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The signed-in account (401 if there's none)."""
    return user_out(db, user)


@router.put("/profile", response_model=UserOut)
def update_profile(profile: ProfileIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Set the display name other members see (the email stays private)."""
    user.display_name = profile.display_name
    db.commit()
    return user_out(db, user)


@router.put("/password", status_code=204)
def change_password(change: PasswordChange, request: Request,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Change the password; other browsers are signed out."""
    with roster_errors(db):
        accounts.change_password(db, user, change.current_password, change.new_password,
                                 keep_token=request.cookies.get(SESSION_COOKIE, ""))


@router.delete("/account", status_code=204)
def delete_account(confirm: AccountDeletion, response: Response,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the account and every league in it, after checking the password."""
    with roster_errors(db):
        accounts.delete_account(db, user, confirm.password)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/forgot", status_code=202)
def forgot_password(request: ResetRequest, background: BackgroundTasks,
                    db: Session = Depends(get_db)) -> dict[str, str]:
    """Email a one-time reset link (good for an hour) to the account's address. The
    answer is the same whether or not the account exists."""
    key = f"reset:{accounts.normalize_email(request.email)}"
    answer = {"detail": "If there's an account for that email, a reset link is on its way."}
    if resets.blocked(key):
        return answer
    resets.failed(key)
    found = accounts.request_reset(db, request.email)
    db.commit()
    if found:
        user, token = found
        link = f"{get_settings().site_url.rstrip('/')}/reset-password?token={token}"
        background.add_task(
            email.send, user.email, "Reset your Dynasty Football password",
            "Someone (hopefully you) asked to reset the password for this account.\n\n"
            f"Choose a new password here (the link works once, for an hour):\n{link}\n\n"
            "If it wasn't you, ignore this email: your password stays as it is.")
    return answer


@router.post("/reset", status_code=204)
def reset_password(reset: PasswordResetIn, db: Session = Depends(get_db)):
    """Set a new password with a reset link's token; the account is signed out
    everywhere, and signs in again with the new password."""
    with roster_errors(db):
        accounts.reset_password(db, reset.token, reset.password)
