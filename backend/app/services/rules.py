"""League rules (docs/design/head-to-head-and-commissioner.md §4): roster size, the salary cap
and how it grows, playoff seeds per conference, and the regular season's length. The
commissioner changes them between seasons only (after the champion is crowned, before week 1
is played), so a season is never played under two sets of rules.

- Roster size counts at once (AI teams over a lower limit in the preseason cut down now;
  members cut before week 1, as ever).
- The cap counts at once; its growth is applied at each offseason (services/offseason.py).
- Playoff seeds count for the coming season's playoffs; byes follow from the count.
- Season length: before the new season's first game, its schedule is drawn again; in the
  old season's offseason, it's the length of the next schedule.
"""

import random

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.playoffs import pair_round, seed_count
from app.models import CoachedGame, Conference, Division, Game, League, LiveGame, Season, Team
from app.schemas import RulesIn, RulesOut
from app.services.errors import RosterError
from app.services.members import human_team_ids
from app.services.teams import current_season

ROSTER_SIZES = (45, 60)
SEED_CHOICES = (2, 3, 4, 5, 6, 7, 8)
MAX_WEEKS = 20
LOCKED = ("regular_season", "playoffs")


def fields(league: League) -> dict:
    """The rules as the League log shows a change to them."""
    return {"roster_max": league.roster_max, "salary_cap": league.salary_cap,
            "cap_growth_bp": league.cap_growth_bp, "playoff_seeds": league.playoff_seeds,
            "season_weeks": league.season_weeks, "firing": league.firing}


def _smallest_conference(db: Session, league_id: int) -> int:
    sizes = db.execute(select(func.count(Team.id)).join(Team.division).join(Division.conference)
                       .where(Conference.league_id == league_id)
                       .group_by(Conference.id)).scalars().all()
    return min(sizes, default=0)


def _weeks(db: Session, season: Season | None) -> int:
    if season is None:
        return 0
    return db.scalar(select(func.max(Game.week)).where(Game.season_id == season.id,
                                                       Game.stage == "regular")) or 0


def locked_reason(season: Season | None) -> str | None:
    if season is not None and season.phase in LOCKED:
        return ("League rules change between seasons: after the champion is crowned and "
                "before week 1 is played.")
    return None


def rules_view(db: Session, league: League) -> RulesOut:
    season = current_season(db, league.id)
    conference = _smallest_conference(db, league.id)
    seeds = seed_count(conference, league.playoff_seeds)
    byes, _games = pair_round(list(range(1, seeds + 1)))
    return RulesOut(
        roster_max=league.roster_max, salary_cap=league.salary_cap,
        cap_growth_pct=league.cap_growth_bp / 100, playoff_seeds=league.playoff_seeds,
        seeds=seeds, byes=len(byes),
        seed_choices=[n for n in SEED_CHOICES if n <= conference],
        season_weeks=league.season_weeks or _weeks(db, season), max_weeks=MAX_WEEKS,
        firing=league.firing,
        locked_reason=locked_reason(season))


def update(db: Session, league: League, rules: RulesIn) -> None:
    """Change the rules (between seasons only), and apply what counts at once."""
    season = current_season(db, league.id)
    problem = locked_reason(season)
    if problem:
        raise RosterError(problem)
    changes = rules.model_dump(exclude_unset=True)
    if "roster_max" in changes:
        size = changes["roster_max"]
        if size is None or not ROSTER_SIZES[0] <= size <= ROSTER_SIZES[1]:
            raise RosterError(f"A roster is {ROSTER_SIZES[0]} to {ROSTER_SIZES[1]} players.", 422)
    if "playoff_seeds" in changes:
        seeds = changes["playoff_seeds"]
        conference = _smallest_conference(db, league.id)
        if seeds is not None and (seeds not in SEED_CHOICES or seeds > conference):
            raise RosterError(f"Seeds per conference: one of "
                              f"{', '.join(str(n) for n in SEED_CHOICES if n <= conference)}, "
                              "or automatic.", 422)
        league.playoff_seeds = seeds
    if "season_weeks" in changes:
        weeks = changes["season_weeks"]
        if weeks is None or not 1 <= weeks <= MAX_WEEKS:
            raise RosterError(f"A regular season is 1 to {MAX_WEEKS} weeks.", 422)
    if "firing" in changes:
        from app.services.careers import FIRINGS

        if changes["firing"] not in FIRINGS:
            raise RosterError("Firing is automatic, on or off.", 422)
        league.firing = changes["firing"]
    for name in ("salary_cap", "cap_growth_pct"):
        if name in changes and changes[name] is None:
            raise RosterError("Give a value for each rule you change.", 422)

    if "salary_cap" in changes:
        league.salary_cap = changes["salary_cap"]
    if "cap_growth_pct" in changes:
        league.cap_growth_bp = round(changes["cap_growth_pct"] * 100)
    if "roster_max" in changes:
        lower = changes["roster_max"] < league.roster_max
        league.roster_max = changes["roster_max"]
        if lower and season is not None and season.phase == "preseason":
            _cut_ai_rosters(db, league)
    if "season_weeks" in changes:
        weeks = changes["season_weeks"]
        league.season_weeks = weeks
        if (season is not None and season.phase in ("free_agency", "draft", "preseason")
                and weeks != _weeks(db, season)):
            _reschedule(db, league, season, weeks)
    db.flush()


def _cut_ai_rosters(db: Session, league: League) -> None:
    """In the preseason, AI teams over a lower roster limit cut down now (members before
    week 1, as ever)."""
    from app.services.draft import cut_down  # (the draft builds on the season services)

    humans = human_team_ids(db, league.id)
    for team in db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)):
        if team.id not in humans:
            cut_down(db, team)


def _reschedule(db: Session, league: League, season: Season, weeks: int) -> None:
    """Draw the coming season's schedule again at its new length (no game played yet)."""
    from app.seed.generator import _schedule

    games = select(Game.id).where(Game.season_id == season.id)
    if db.scalar(select(Game.id).where(Game.season_id == season.id,
                                       Game.status != "scheduled").limit(1)):
        raise RosterError("This season's games have started: the length counts from the next.")
    db.execute(delete(LiveGame).where(LiveGame.game_id.in_(games)))
    db.execute(delete(CoachedGame).where(CoachedGame.game_id.in_(games)))
    db.execute(delete(Game).where(Game.season_id == season.id))
    team_ids = sorted(db.scalars(select(Team.id).where(Team.league_id == league.id)))
    _schedule(db, season, team_ids, random.Random(f"schedule:{league.id}:{season.year}:{weeks}"),
              weeks)
