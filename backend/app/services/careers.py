"""Job security (docs/design/owners-and-front-offices.md §4): owners fire general managers who
let them down, and a fired member takes another job, keeping their career record.

- At the owner's review (services/owners.py), an owner whose confidence ends below
  `FIRE_LINE` fires the general manager, if the league's rule allows it (`fires`). An AI
  team's GM is replaced at once (the owner starts again); a member is told, and chooses
  from the open jobs before the offseason begins (`take_job`; their old team goes to the AI).
- Open jobs: AI teams whose owners just fired their GM, topped up to `MIN_JOBS` with the
  AI owners least happy with theirs.
- A member's career is their stints (`GmStint`); one who never moved has been with their
  team since the league's first season.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import owners as owner_rules
from app.models import (
    Franchise,
    GmStint,
    League,
    Owner,
    OwnerSeason,
    PlayoffSeed,
    Season,
    Team,
    User,
)
from app.schemas import GmCareerOut, GmJobOut, GmStintOut
from app.services.errors import RosterError
from app.services.members import display_name, human_team_ids
from app.services.serializers import team_summary
from app.services.standings import compute_records
from app.services.teams import (
    current_season,
    load_overrides,
    load_roster,
    team_lineup,
    team_ratings,
)

FIRINGS = ("auto", "on", "off")
MIN_JOBS = 3


def _now() -> datetime:
    return datetime.now(UTC)


def fires(league: League, team_id: int, humans: set[int]) -> bool:
    """Whether the league lets an owner fire this team's GM: AI teams' unless firing is
    off; members' when it's on, or (automatic) when only one member runs a team."""
    if league.firing == "off":
        return False
    if team_id not in humans:
        return True
    return league.firing == "on" or len(humans) <= 1


def after_review(db: Session, league: League, row: OwnerSeason, owner: Owner,
                 humans: set[int]) -> None:
    """The owner's decision once the season's reviewed (called by owners.review)."""
    if row.confidence_after is None or row.confidence_after >= owner_rules.FIRE_LINE:
        return
    if not fires(league, row.team_id, humans):
        return
    row.fired = True
    if row.team_id not in humans:
        owner.confidence = owner_rules.START_CONFIDENCE  # (a new general manager)
        return
    franchise = db.scalar(select(Franchise).where(Franchise.league_id == league.id,
                                                  Franchise.team_id == row.team_id))
    franchise.fired_at = _now()
    from app.services.notifications import notify  # (notifications build on members)

    team = db.get(Team, row.team_id)
    notify(db, franchise.user_id, "job", f"You've been fired by the {team.full_name}",
           "Choose your next job from the teams looking for a general manager.",
           league_id=league.id, link="/career", key=f"fired:{row.id}")


def undo_firings(db: Session, league_id: int) -> None:
    """A rolled-back final: members fired at its review are back in their jobs."""
    for franchise in db.scalars(select(Franchise).where(Franchise.league_id == league_id,
                                                        Franchise.fired_at.is_not(None))):
        franchise.fired_at = None


def moved_since(db: Session, season: Season) -> bool:
    """Has a member taken another job since `season` ended?"""
    return db.scalar(select(GmStint.id).where(GmStint.league_id == season.league_id,
                                              GmStint.from_year == season.year + 1)
                     .limit(1)) is not None


def pending(db: Session, league_id: int) -> list[Franchise]:
    """Members fired and still to choose their next job."""
    return list(db.scalars(select(Franchise).where(Franchise.league_id == league_id,
                                                   Franchise.fired_at.is_not(None))))


def settle_before_offseason(db: Session, league: League, autopilot: bool) -> None:
    """Before the offseason: a fired member must have chosen their next job. On autopilot
    (sim ahead) members aren't fired: the owner keeps them, starting again."""
    waiting = pending(db, league.id)
    if not waiting:
        return
    if autopilot:
        for franchise in waiting:
            franchise.fired_at = None
            owner = db.scalar(select(Owner).where(Owner.team_id == franchise.team_id))
            owner.confidence = owner_rules.START_CONFIDENCE
        db.flush()
        return
    names = ", ".join(display_name(db.get(User, f.user_id)) for f in waiting)
    raise RosterError(f"Fired general managers choose their next job first ({names}): "
                      "the Career page lists the open jobs.")


# ---------- open jobs ----------

def _reviewed(db: Session, league_id: int) -> Season | None:
    return db.scalar(select(Season).join(OwnerSeason, OwnerSeason.season_id == Season.id)
                     .where(Season.league_id == league_id, OwnerSeason.results.is_not(None))
                     .order_by(Season.year.desc()).limit(1))


def open_jobs(db: Session, league: League) -> list[tuple[Team, str]]:
    """AI teams looking for a general manager: those whose owners just fired theirs, then
    (up to `MIN_JOBS`) those whose owners are least happy with theirs."""
    humans = human_team_ids(db, league.id)
    season = _reviewed(db, league.id)
    fired = set(db.scalars(select(OwnerSeason.team_id).where(
        OwnerSeason.season_id == season.id, OwnerSeason.fired))) if season else set()
    owners = {o.team_id: o for o in db.scalars(select(Owner).where(Owner.league_id == league.id))}
    teams = {t.id: t for t in league.teams if t.id not in humans}
    jobs = [(teams[tid], "The owner just fired the general manager.")
            for tid in sorted(fired) if tid in teams]
    unhappy = sorted((tid for tid in teams if tid not in fired and tid in owners),
                     key=lambda tid: (owners[tid].confidence, tid))
    for tid in unhappy[:max(0, MIN_JOBS - len(jobs))]:
        jobs.append((teams[tid], "The owner wants a change."))
    return jobs


def _job_out(db: Session, team: Team, why: str, ratings: dict[int, int]) -> GmJobOut:
    owner = db.scalar(select(Owner).where(Owner.team_id == team.id))
    ranked = sorted(ratings, key=lambda tid: (-ratings[tid], tid))
    place = owner_rules.situation(ranked.index(team.id) + 1, len(ranked))
    season = _reviewed(db, team.league_id)
    record = compute_records(db, season, [team.id])[team.id] if season else None
    return GmJobOut(team=team_summary(team), why=why, owner=owner.full_name if owner else "",
                  wants=owner_rules.PRIORITIES[owner.priority] if owner else "",
                  patience=owner.patience if owner else 3, market=team.market or "medium",
                  fan_mood=team.fan_mood if team.fan_mood is not None else 50,
                  rating=ratings[team.id], situation=place,
                  last_season=(f"{record.wins}-{record.losses}"
                               + (f"-{record.ties}" if record.ties else "")) if record else None)


def take_job(db: Session, franchise: Franchise, team_id: int) -> None:
    """A fired member takes one of the open jobs; their old team goes to the AI."""
    from app.services.season import active_job  # (the season services build on this)

    if franchise.fired_at is None:
        raise RosterError("You haven't been fired: your owner still wants you.")
    league = franchise.league
    if active_job(db, league.id) is not None:
        raise RosterError("A simulation is running in this league.")
    team = next((t for t, _ in open_jobs(db, league) if t.id == team_id), None)
    if team is None:
        raise RosterError("That team isn't looking for a general manager.", 404)
    season = current_season(db, league.id)
    old = franchise.team_id
    for stint in _stints(db, franchise):
        if stint.to_year is None:
            stint.to_year, stint.ended = season.year, "fired"
            if stint.id is None:
                db.add(stint)
    db.add(GmStint(league_id=league.id, user_id=franchise.user_id, team_id=team.id,
                   from_year=season.year + 1))
    for tid in (old, team.id):  # (both owners start again with a new general manager)
        db.scalar(select(Owner).where(Owner.team_id == tid)).confidence = \
            owner_rules.START_CONFIDENCE
    franchise.team_id = team.id
    franchise.name = f"{team.nickname} {league.name}"
    franchise.fired_at = None
    franchise.activated_at = _now()
    db.flush()
    from app.services.notifications import notify_members  # (it builds on members)

    user = db.get(User, franchise.user_id)
    notify_members(db, league.id, "job", f"{display_name(user)} is the new general manager of "
                   f"the {team.full_name}", f"The {db.get(Team, old).full_name} go to the AI.",
                   "/league", skip={user.id})


# ---------- the career record ----------

def _stints(db: Session, franchise: Franchise) -> list[GmStint]:
    stints = list(db.scalars(select(GmStint).where(GmStint.league_id == franchise.league_id,
                                                   GmStint.user_id == franchise.user_id)
                             .order_by(GmStint.from_year, GmStint.id)))
    if not stints:  # (never moved: with this team since the league's first season)
        first = db.scalar(select(Season.year).where(Season.league_id == franchise.league_id)
                          .order_by(Season.year).limit(1))
        stints = [GmStint(league_id=franchise.league_id, user_id=franchise.user_id,
                          team_id=franchise.team_id, from_year=first or 0)]
    return stints


def career_view(db: Session, franchise: Franchise) -> GmCareerOut:
    league = franchise.league
    seasons = {s.year: s for s in db.scalars(select(Season).where(Season.league_id == league.id))}
    rows, totals = [], {"wins": 0, "losses": 0, "ties": 0, "playoffs": 0, "titles": 0}
    for stint in _stints(db, franchise):
        last = stint.to_year if stint.to_year is not None else max(seasons, default=0)
        line = {"wins": 0, "losses": 0, "ties": 0, "playoffs": 0, "titles": 0}
        years = [y for y in range(stint.from_year, last + 1) if y in seasons]
        for year in years:
            season = seasons[year]
            record = compute_records(db, season, [stint.team_id])[stint.team_id]
            line["wins"] += record.wins
            line["losses"] += record.losses
            line["ties"] += record.ties
            line["playoffs"] += db.scalar(select(PlayoffSeed.id).where(
                PlayoffSeed.season_id == season.id, PlayoffSeed.team_id == stint.team_id)
                .limit(1)) is not None
            line["titles"] += season.champion_team_id == stint.team_id
        for key in totals:
            totals[key] += line[key]
        rows.append(GmStintOut(team=team_summary(db.get(Team, stint.team_id)),
                                   from_year=stint.from_year, to_year=stint.to_year,
                                   seasons=len(years), ended=stint.ended, **line))
    jobs = []
    if franchise.fired_at is not None:
        teams = list(db.scalars(select(Team).where(Team.league_id == league.id)))
        overrides = load_overrides(db, [t.id for t in teams])
        ratings = {t.id: team_ratings(team_lineup(load_roster(db, t.id),
                                                  overrides[t.id])).overall for t in teams}
        jobs = [_job_out(db, team, why, ratings) for team, why in open_jobs(db, league)]
    return GmCareerOut(name=display_name(db.get(User, franchise.user_id)),
                     team=team_summary(db.get(Team, franchise.team_id)),
                     fired=franchise.fired_at is not None, stints=rows,
                     firings=sum(1 for r in rows if r.ended == "fired"), **totals,
                     open_jobs=jobs, firing=league.firing)
