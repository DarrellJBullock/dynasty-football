"""The season together (docs/design/leagues-with-friends.md §4): managers say they're ready
for the next step of the season, and the commissioner advances it (one week, playoff
round, the offseason, a market day, or the draft to the next manager on the clock), or the
league advances itself once a day at a set time. The draft clock lives in services/draft.py.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import League, LeagueMember, Season, Team, User
from app.schemas import LeagueSettingsIn, SimulateRequest, TurnMember, TurnOut
from app.services import draft, free_agency, offseason, playoffs
from app.services import season as season_service
from app.services.errors import RosterError
from app.services.members import display_name, human_team_ids, member, user_team_id
from app.services.serializers import team_summary
from app.services.teams import current_season

log = logging.getLogger("app.turns")

DRAFT_CLOCKS = (2, 5, 15, 60, 240, 720, 1440)  # minutes a manager may choose from


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def step_key(db: Session, season: Season) -> str:
    """The step of the season that's next: managers are ready for one step at a time."""
    if season.phase in ("preseason", "regular_season"):
        if season.current_week <= season_service.season_weeks(db, season.id):
            return f"{season.id}:week:{season.current_week}"
        return f"{season.id}:playoffs:{playoffs.rounds_left(db, season)}"
    if season.phase == "playoffs":
        return f"{season.id}:playoffs:{playoffs.rounds_left(db, season)}"
    if season.phase == "free_agency":
        return f"{season.id}:market:{season.free_agency_day}"
    return f"{season.id}:{season.phase}"


def step_label(db: Session, season: Season) -> str:
    """What advancing does next, for people."""
    view = season_service.season_view(db, season)
    if season.phase == "offseason":
        return "The offseason"
    if season.phase == "free_agency":
        return f"Free agency, day {season.free_agency_day or 1}"
    if season.phase == "draft":
        return "The draft"
    if view.regular_season_complete:
        return view.next_round or "The playoffs"
    return f"Week {season.current_week}"


def _managers(db: Session, league: League) -> list[tuple[LeagueMember, Team]]:
    """Members who run a team, in team order."""
    rows = []
    for joined in db.scalars(select(LeagueMember).where(LeagueMember.league_id == league.id)
                             .order_by(LeagueMember.joined_at, LeagueMember.id)):
        team_id = user_team_id(db, league.id, joined.user)
        if team_id is not None:
            rows.append((joined, db.get(Team, team_id)))
    return rows


def next_advance_at(league: League, now: datetime | None = None) -> datetime | None:
    """The next time the league advances itself (None: it doesn't)."""
    if league.advance_minute_utc is None:
        return None
    now = now or _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    at = today + timedelta(minutes=league.advance_minute_utc)
    return at if at > now else at + timedelta(days=1)


def _last_scheduled(league: League, now: datetime) -> datetime:
    """The most recent scheduled time at or before `now`."""
    return next_advance_at(league, now) - timedelta(days=1)


def turn_view(db: Session, league: League, user: User) -> TurnOut:
    season = current_season(db, league.id)
    if season is None:
        raise RosterError("The league has no season.", 404)
    key = step_key(db, season)
    managers = [TurnMember(member_id=m.id, display_name=display_name(m.user),
                           team=team_summary(team), ready=m.ready_for == key,
                           is_you=m.user_id == user.id)
                for m, team in _managers(db, league)]
    you = member(db, league.id, user)
    clock = draft.clock_ends_at(db, season)
    return TurnOut(step=step_label(db, season), step_key=key, managers=managers,
                   all_ready=all(m.ready for m in managers),
                   draft_clock_minutes=league.draft_clock_minutes,
                   advance_minute_utc=league.advance_minute_utc,
                   next_advance_at=next_advance_at(league),
                   pick_clock_ends_at=clock,
                   can_advance=you is not None and you.role == "commissioner")


def set_ready(db: Session, league: League, user: User, ready: bool) -> None:
    """A manager is ready for the next step (or not, any more)."""
    you = member(db, league.id, user)
    if you is None or user_team_id(db, league.id, user) is None:
        raise RosterError("You don't run a team in this league.", 403)
    you.ready_for = step_key(db, current_season(db, league.id)) if ready else None
    db.flush()


def update_settings(db: Session, league: League, settings: LeagueSettingsIn) -> None:
    changes = settings.model_dump(exclude_unset=True)
    if "draft_clock_minutes" in changes:
        if changes["draft_clock_minutes"] not in DRAFT_CLOCKS:
            raise RosterError("Pick one of the draft clocks offered.", 422)
        league.draft_clock_minutes = changes["draft_clock_minutes"]
    if "advance_minute_utc" in changes:
        minute = changes["advance_minute_utc"]
        if minute is not None and not 0 <= minute < 24 * 60:
            raise RosterError("A time of day is 0 to 1439 minutes after midnight.", 422)
        league.advance_minute_utc = minute
        league.auto_advanced_at = _now()  # (counting from now: setting it never advances)
    db.flush()


def advance(db: Session, league: League) -> str:
    """Advance the league one step; returns what was played. Refused while a background
    sim is running."""
    if season_service.active_job(db, league.id) is not None:
        raise RosterError("A simulation is running in this league.")
    season = current_season(db, league.id)
    if season is None:
        raise RosterError("The league has no season.", 404)
    label = step_label(db, season)
    if season.phase == "offseason":
        offseason.advance(db, season)
    elif season.phase == "free_agency":
        free_agency.play_days(db, season, "next_day")
    elif season.phase == "draft":
        draft.draft_view(db, league)  # (generates the class if it isn't there)
        draft.play(db, season, "my_pick")
    else:
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
    db.flush()
    return label


def multiplayer(db: Session, league_id: int) -> bool:
    """More than one member runs a team: the season moves together, a step at a time."""
    return len(human_team_ids(db, league_id)) > 1


def tick(db: Session, now: datetime | None = None) -> int:
    """The worker's minute: run out expired draft clocks, and advance leagues whose daily
    time has come. Commits each league on its own. Returns how many leagues it changed."""
    now = now or _now()
    changed = 0
    drafting = db.scalars(select(Season).where(Season.phase == "draft",
                                               Season.pick_clock_started_at.is_not(None))).all()
    for season in drafting:
        if draft.run_clock(db, season, now):
            db.commit()
            changed += 1
    for league in db.scalars(select(League).where(League.advance_minute_utc.is_not(None))).all():
        due = _last_scheduled(league, now)
        if league.auto_advanced_at is not None and _as_utc(league.auto_advanced_at) >= due:
            continue
        league.auto_advanced_at = now
        try:
            label = advance(db, league)
        except RosterError as exc:  # e.g. a sim running, or a roster to fix: try tomorrow
            db.rollback()
            league = db.get(League, league.id)
            league.auto_advanced_at = now
            log.info("league %s didn't advance itself: %s", league.id, exc.message,
                     extra={"league_id": league.id})
        else:
            log.info("league %s advanced itself: %s", league.id, label,
                     extra={"league_id": league.id})
            changed += 1
        db.commit()
    return changed
