"""Who belongs to a league and what they run (docs/design/leagues-with-friends.md §3).

A league has members: commissioners (who run the league) and managers (who run a team).
A member's team is their Franchise; teams nobody runs are the AI's. Invite links let
people join: anyone signed in who opens one can pick an open team. Only the SHA-256 of an
invite's token is stored.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Franchise, League, LeagueInvite, LeagueMember, Team, User
from app.schemas import InviteOut, InvitePreview, MemberOut, MembersOut
from app.services.errors import RosterError
from app.services.serializers import league_out, team_summary

ROLES = ("commissioner", "manager")
INVITE_DAYS = 7


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def member(db: Session, league_id: int, user: User) -> LeagueMember | None:
    return db.scalar(select(LeagueMember).where(LeagueMember.league_id == league_id,
                                                LeagueMember.user_id == user.id))


def is_commissioner(db: Session, league_id: int, user: User) -> bool:
    m = member(db, league_id, user)
    return m is not None and m.role == "commissioner"


def user_team_id(db: Session, league_id: int, user: User | None) -> int | None:
    """The team `user` runs in the league (None: they don't run one, or no user)."""
    if user is None:
        return None
    return db.scalar(select(Franchise.team_id).where(Franchise.league_id == league_id,
                                                     Franchise.user_id == user.id))


def human_team_ids(db: Session, league_id: int) -> set[int]:
    """Every team a member runs: the AI leaves these to their managers."""
    return set(db.scalars(select(Franchise.team_id).where(Franchise.league_id == league_id)))


def manager_of(db: Session, team_id: int) -> int | None:
    """The user who runs a team (None: the AI)."""
    return db.scalar(select(Franchise.user_id).where(Franchise.team_id == team_id))


def can_run_team(db: Session, team: Team, user: User) -> bool:
    """A member may act for their own team; a commissioner also for any team a member
    runs (standing in for an absent manager). AI teams are the AI's."""
    if user_team_id(db, team.league_id, user) == team.id:
        return True
    return is_commissioner(db, team.league_id, user) and manager_of(db, team.id) is not None


def add(db: Session, league: League, user: User, role: str) -> LeagueMember:
    joined = LeagueMember(league_id=league.id, user_id=user.id, role=role)
    db.add(joined)
    db.flush()
    return joined


def give_league(db: Session, league: League, user: User) -> None:
    """Make `user` a league's creator and commissioner, running its unclaimed franchise
    (a new league, the seeded one, or one from before accounts)."""
    league.user_id = user.id
    db.flush()
    for franchise in db.scalars(select(Franchise).where(Franchise.league_id == league.id,
                                                         Franchise.user_id.is_(None))).all():
        franchise.user_id = user.id
        break  # (one each: any others stay unclaimed)
    if member(db, league.id, user) is None:
        add(db, league, user, "commissioner")
    db.flush()


def league_ids(db: Session, user: User) -> list[int]:
    """The leagues `user` belongs to."""
    return list(db.scalars(select(LeagueMember.league_id).where(LeagueMember.user_id == user.id)
                           .order_by(LeagueMember.league_id)))


def leave_all(db: Session, user: User) -> list[League]:
    """Before an account is deleted: leave every league that has other members (handing
    the commissioner's role and the creator's place on), and return the leagues that are
    only theirs (to delete)."""
    alone = []
    for league in db.scalars(select(League).join(LeagueMember).where(
            LeagueMember.user_id == user.id).order_by(League.id)).all():
        others = list(db.scalars(select(LeagueMember).where(
            LeagueMember.league_id == league.id, LeagueMember.user_id != user.id)
            .order_by(LeagueMember.joined_at, LeagueMember.id)))
        if not others:
            alone.append(league)
            continue
        if not any(m.role == "commissioner" for m in others):
            others[0].role = "commissioner"
        if league.user_id == user.id:
            league.user_id = next(m.user_id for m in others if m.role == "commissioner")
        db.flush()
        remove(db, league, user, member(db, league.id, user).id)
    return alone


def display_name(user: User) -> str:
    """What other members see: the display name, or the part of the email before the @."""
    return user.display_name or user.email.split("@")[0]


# ---------- invites ----------

def create_invite(db: Session, league: League, user: User) -> tuple[LeagueInvite, str]:
    """A new invite link's token (shown once; only its hash is kept)."""
    token = secrets.token_urlsafe(24)
    invite = LeagueInvite(league_id=league.id, token_hash=_hash(token), created_by=user.id,
                          expires_at=_now() + timedelta(days=INVITE_DAYS))
    db.add(invite)
    db.flush()
    return invite, token


def open_invites(db: Session, league_id: int) -> list[LeagueInvite]:
    invites = db.scalars(select(LeagueInvite).where(
        LeagueInvite.league_id == league_id, LeagueInvite.revoked_at.is_(None))
        .order_by(LeagueInvite.created_at.desc(), LeagueInvite.id.desc()))
    return [i for i in invites if _as_utc(i.expires_at) > _now()]  # (SQLite: compare here)


def revoke_invite(db: Session, league_id: int, invite_id: int) -> None:
    invite = db.get(LeagueInvite, invite_id)
    if invite is None or invite.league_id != league_id:
        raise RosterError("Invite not found.", 404)
    invite.revoked_at = _now()
    db.flush()


def invite_for(db: Session, token: str) -> LeagueInvite:
    """The open invite a token names (404 for a wrong, expired or revoked link, alike)."""
    invite = db.scalar(select(LeagueInvite).where(LeagueInvite.token_hash == _hash(token)))
    if invite is None or invite.revoked_at is not None or _as_utc(invite.expires_at) <= _now():
        raise RosterError("This invite link isn't valid any more. Ask for a new one.", 404)
    return invite


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def open_teams(db: Session, league_id: int) -> list[Team]:
    """Teams nobody runs yet."""
    taken = human_team_ids(db, league_id)
    return [t for t in db.scalars(select(Team).where(Team.league_id == league_id).order_by(Team.id))
            if t.id not in taken]


def join(db: Session, token: str, user: User, team_id: int) -> Franchise:
    """Join through an invite as a manager of an open team (or take a team, if already a
    member without one)."""
    from app.services.season import active_job  # (it builds on this module)

    invite = invite_for(db, token)
    league = db.get(League, invite.league_id)
    if active_job(db, league.id) is not None:
        raise RosterError("A simulation is running in this league. Try again when it's done.")
    joined = member(db, league.id, user)
    if joined is not None and user_team_id(db, league.id, user) is not None:
        raise RosterError("You already run a team in this league.")
    team = db.get(Team, team_id)
    if team is None or team.league_id != league.id or team.id in human_team_ids(db, league.id):
        raise RosterError("That team isn't open. Pick another.")
    if joined is None:
        add(db, league, user, "manager")
    invite.uses += 1
    franchise = Franchise(name=f"{team.nickname} {league.name}", league_id=league.id,
                          team_id=team.id, user_id=user.id, activated_at=_now())
    db.add(franchise)
    db.flush()
    from app.services.notifications import notify_members  # (it builds on this module)

    notify_members(db, league.id, "member_joined", f"{display_name(user)} joined {league.name}",
                   f"They run the {team.full_name}.", "/members", skip={user.id},
                   role="commissioner")
    return franchise


def remove(db: Session, league: League, actor: User, member_id: int) -> None:
    """A member leaves (removing themselves) or a commissioner removes them; their team
    goes back to the AI. The last commissioner can't go while others remain."""
    gone = db.get(LeagueMember, member_id)
    if gone is None or gone.league_id != league.id:
        raise RosterError("Member not found.", 404)
    if gone.user_id != actor.id and not is_commissioner(db, league.id, actor):
        raise RosterError("Only a commissioner can remove someone else.", 403)
    others = db.scalar(select(func.count(LeagueMember.id)).where(
        LeagueMember.league_id == league.id, LeagueMember.id != gone.id)) or 0
    commissioners = db.scalar(select(func.count(LeagueMember.id)).where(
        LeagueMember.league_id == league.id, LeagueMember.role == "commissioner",
        LeagueMember.id != gone.id)) or 0
    if others == 0:
        raise RosterError("You're the only member: delete the league instead.")
    if gone.role == "commissioner" and commissioners == 0:
        raise RosterError("Make someone else a commissioner first.")
    franchise = db.scalar(select(Franchise).where(Franchise.league_id == league.id,
                                                  Franchise.user_id == gone.user_id))
    if franchise is not None:
        db.delete(franchise)
    db.delete(gone)
    db.flush()


def set_role(db: Session, league: League, member_id: int, role: str) -> None:
    if role not in ROLES:
        raise RosterError(f"A role is one of: {', '.join(ROLES)}.", 422)
    changed = db.get(LeagueMember, member_id)
    if changed is None or changed.league_id != league.id:
        raise RosterError("Member not found.", 404)
    if changed.role == "commissioner" and role != "commissioner":
        others = db.scalar(select(func.count(LeagueMember.id)).where(
            LeagueMember.league_id == league.id, LeagueMember.role == "commissioner",
            LeagueMember.id != changed.id)) or 0
        if others == 0:
            raise RosterError("A league needs a commissioner: make someone else one first.")
    changed.role = role
    db.flush()


# ---------- views ----------

def _member_out(db: Session, joined: LeagueMember, you: User) -> MemberOut:
    team_id = user_team_id(db, joined.league_id, joined.user)
    return MemberOut(id=joined.id, display_name=display_name(joined.user), role=joined.role,
                     team=team_summary(db.get(Team, team_id)) if team_id else None,
                     is_you=joined.user_id == you.id, joined_at=joined.joined_at)


def members_view(db: Session, league: League, user: User) -> MembersOut:
    """The league's members (commissioners first), its open teams, and, for a
    commissioner, its open invite links."""
    everyone = db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)
                          .order_by(LeagueMember.role, LeagueMember.joined_at,
                                    LeagueMember.id)).all()
    rows = [_member_out(db, m, user) for m in everyone]
    you = next(r for r in rows if r.is_you)
    invites = open_invites(db, league.id) if you.role == "commissioner" else []
    return MembersOut(
        league=league_out(league), you=you, members=rows,
        invites=[InviteOut(id=i.id, created_at=i.created_at, expires_at=i.expires_at,
                           uses=i.uses) for i in invites],
        open_teams=[team_summary(t) for t in open_teams(db, league.id)])


def invite_preview(db: Session, token: str, user: User) -> InvitePreview:
    invite = invite_for(db, token)
    league = db.get(League, invite.league_id)
    commissioner = db.scalar(select(LeagueMember).where(
        LeagueMember.league_id == league.id, LeagueMember.role == "commissioner")
        .order_by(LeagueMember.joined_at, LeagueMember.id))
    count = db.scalar(select(func.count(LeagueMember.id)).where(
        LeagueMember.league_id == league.id)) or 0
    yours = user_team_id(db, league.id, user)
    return InvitePreview(
        league=league_out(league),
        commissioner=display_name(commissioner.user) if commissioner else "",
        member_count=count, open_teams=[team_summary(t) for t in open_teams(db, league.id)],
        already_member=member(db, league.id, user) is not None,
        your_team=team_summary(db.get(Team, yours)) if yours else None)
