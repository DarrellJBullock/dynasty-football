"""A league's members and invite links (docs/design/leagues-with-friends.md §3)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.access import current_user
from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.db import get_db
from app.models import League, LeagueMember, User
from app.schemas import (
    FranchiseOut,
    InviteCreated,
    InvitePreview,
    InviteToken,
    JoinRequest,
    MembersOut,
    RoleChange,
    ShareLinkOut,
)
from app.services import league_log, sharing
from app.services import members as member_service
from app.services.dashboard import franchise_out

router = APIRouter(tags=["members"])


@router.get("/leagues/{league_id}/members", response_model=MembersOut)
def members(league: League = Depends(get_league), user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """Who's in the league and which teams they run, the teams still open, and (for a
    commissioner) the open invite links."""
    return member_service.members_view(db, league, user)


@router.post("/leagues/{league_id}/invites", response_model=InviteCreated, status_code=201)
def create_invite(league: League = Depends(get_league), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """A new invite link, good for a week. Its token is shown only now."""
    with roster_errors(db):
        invite, token = member_service.create_invite(db, league, user)
    return InviteCreated(id=invite.id, created_at=invite.created_at,
                         expires_at=invite.expires_at, uses=invite.uses, token=token)


@router.delete("/leagues/{league_id}/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, league: League = Depends(get_league),
                  db: Session = Depends(get_db)):
    with roster_errors(db):
        member_service.revoke_invite(db, league.id, invite_id)


@router.patch("/leagues/{league_id}/members/{member_id}", response_model=MembersOut)
def set_role(member_id: int, change: RoleChange, league: League = Depends(get_league),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    with roster_errors(db):
        member = db.get(LeagueMember, member_id)
        before = member.role if member is not None else None
        member_service.set_role(db, league, member_id, change.role)
        if before != change.role:
            name = member_service.display_name(db.get(User, member.user_id))
            league_log.record(db, league.id, user, "member",
                              f"Made {name} a {change.role}",
                              [{"field": "role", "before": before, "after": change.role}])
    return member_service.members_view(db, league, user)


@router.delete("/leagues/{league_id}/members/{member_id}", status_code=204)
def remove_member(member_id: int, league: League = Depends(get_league),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Leave the league (your own membership), or, as a commissioner, remove someone:
    their team goes back to the AI."""
    with roster_errors(db):
        member = db.get(LeagueMember, member_id)
        gone = db.get(User, member.user_id) if member is not None else None
        someone_else = gone is not None and gone.id != user.id
        name = member_service.display_name(gone) if someone_else else ""
        team_id = member_service.user_team_id(db, league.id, gone) if someone_else else None
        member_service.remove(db, league, user, member_id)
        if someone_else:
            league_log.record(db, league.id, user, "member",
                              f"Removed {name} from the league (their team goes to the AI)",
                              team_id=team_id)


# The invite's token travels in the body, never the URL, so it stays out of logs.
invites_router = APIRouter(prefix="/invites", tags=["members"])


@invites_router.post("/preview", response_model=InvitePreview)
def preview(body: InviteToken, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    """The league an invite link is for, and its open teams."""
    with roster_errors(db):
        return member_service.invite_preview(db, body.token, user)


@invites_router.post("/join", response_model=FranchiseOut, status_code=201)
def join(body: JoinRequest, user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """Join the league and take an open team; it becomes your active franchise."""
    with roster_errors(db):
        franchise = member_service.join(db, body.token, user, body.team_id)
    return franchise_out(db, franchise)


# ---------- sharing and export (services/sharing.py) ----------

@router.post("/leagues/{league_id}/share", response_model=ShareLinkOut, status_code=201)
def share(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """A read-only public link to the league (shown once); any earlier link stops working."""
    with roster_errors(db):
        token = sharing.create_link(db, league)
    return ShareLinkOut(token=token, shared_at=league.shared_at)


@router.delete("/leagues/{league_id}/share", status_code=204)
def unshare(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Stop sharing: the public link stops working."""
    with roster_errors(db):
        sharing.revoke_link(db, league)


@router.get("/leagues/{league_id}/export")
def export(league: League = Depends(get_league), db: Session = Depends(get_db)) -> JSONResponse:
    """The whole league as one JSON file (docs/league-export.md)."""
    return JSONResponse(sharing.export_league(db, league), headers={
        "Content-Disposition": f'attachment; filename="{sharing.export_filename(league)}"'})
