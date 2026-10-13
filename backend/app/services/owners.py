"""Owners and fans (docs/design/owners-and-front-offices.md §3; the rules: domain/owners.py).

- Every team gets an owner and a market once per league (`ensure_owners`), from its own
  `random.Random(f"owners:{league.id}")`, never the generator's stream.
- Each season's goals are set when the preseason opens (`set_goals`), from the owner's
  priority and where the team's roster stands among the league's.
- When the champion is crowned, every owner reviews the season (`review`): the goals met or
  missed and the fans move their confidence; the fans' mood is stored for next season. A
  rolled-back final takes the review back (`unreview`).
- During a season, fan mood and each goal's status are worked out live from the record.
"""

import random
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import owners as rules
from app.models import (
    Game,
    League,
    Owner,
    OwnerSeason,
    PlayoffSeed,
    Season,
    Team,
)
from app.schemas import OwnerGoalOut, OwnerOut, OwnerReviewOut
from app.seed import data
from app.services import money
from app.services.serializers import team_summary
from app.services.standings import compute_records
from app.services.teams import (
    current_season,
    load_overrides,
    load_roster,
    team_lineup,
    team_ratings,
)

LIVE = ("preseason", "regular_season", "playoffs")  # a season with goals being chased


def ensure_owners(db: Session, league: League) -> None:
    """Give every team an owner and a market, once (a league from before owners gets them
    now). The league's row is locked first, so two requests can't both make them."""
    if not db.scalar(select(Owner.id).where(Owner.league_id == league.id).limit(1)):
        db.execute(select(League.id).where(League.id == league.id).with_for_update())
        if not db.scalar(select(Owner.id).where(Owner.league_id == league.id).limit(1)):
            _make(db, league)
    season = current_season(db, league.id)
    if season is not None and season.phase in LIVE:
        set_goals(db, season)


def _make(db: Session, league: League) -> None:
    rng = random.Random(f"owners:{league.id}")
    first = sorted(set(data.FIRST_NAMES) | set(data.FIRST_NAMES_WOMEN))
    teams = sorted(league.teams, key=lambda t: t.id)
    for team, market in zip(teams, rules.markets(rng, len(teams)), strict=True):
        made = rules.make(rng)
        db.add(Owner(league_id=league.id, team_id=team.id, first_name=rng.choice(first),
                     last_name=rng.choice(data.LAST_NAMES), priority=made.priority,
                     patience=made.patience, confidence=rules.START_CONFIDENCE))
        team.market = market
        team.fan_mood = rules.START_FAN_MOOD[market]
    db.flush()


def _weeks(db: Session, season: Season) -> int:
    from app.services.season import season_weeks  # (the season services build on owners)

    return season_weeks(db, season.id)


def set_goals(db: Session, season: Season) -> None:
    """Every owner's goals for `season` (once): from their priority and where the roster
    stands, by team rating, among the league's."""
    have = set(db.scalars(select(OwnerSeason.team_id).where(OwnerSeason.season_id == season.id)))
    owners = {o.team_id: o for o in db.scalars(
        select(Owner).where(Owner.league_id == season.league_id))}
    if not owners or have >= set(owners):
        return
    teams = list(db.scalars(select(Team).where(Team.league_id == season.league_id)
                            .order_by(Team.id)))
    overrides = load_overrides(db, [t.id for t in teams])
    rating = {t.id: team_ratings(team_lineup(load_roster(db, t.id), overrides[t.id])).overall
              for t in teams}
    ranked = sorted(rating, key=lambda tid: (-rating[tid], tid))
    weeks = _weeks(db, season)
    for rank, team_id in enumerate(ranked, start=1):
        if team_id in have or team_id not in owners:
            continue
        place = rules.situation(rank, len(ranked))
        goals = rules.goals(owners[team_id].priority, place, weeks,
                            db.get(League, season.league_id).salary_cap)
        db.add(OwnerSeason(season_id=season.id, team_id=team_id, situation=place,
                           goals=[{"kind": g.kind, "target": g.target, "weight": g.weight}
                                  for g in goals]))
    db.flush()


def _goals(row: OwnerSeason) -> list[rules.Goal]:
    return [rules.Goal(g["kind"], g["target"], g["weight"]) for g in row.goals]


def _facts(db: Session, season: Season,
           team_ids: list[int]) -> dict[int, tuple[rules.Season, money.Finances]]:
    """Each team's season so far: record, playoffs, today's roster (young starters, stars),
    and its money."""
    records = compute_records(db, season, team_ids)
    seeds = {s.team_id: s for s in db.scalars(
        select(PlayoffSeed).where(PlayoffSeed.season_id == season.id))}
    playoff_wins: dict[int, int] = defaultdict(int)
    for game in db.scalars(select(Game).where(Game.season_id == season.id,
                                              Game.stage == "playoff", Game.status == "final")):
        winner = (game.home_team_id if (game.home_score or 0) > (game.away_score or 0)
                  else game.away_team_id)
        playoff_wins[winner] += 1
    overrides = load_overrides(db, team_ids)
    weeks = _weeks(db, season)
    facts = {}
    for team_id in team_ids:
        roster = load_roster(db, team_id)
        lineup = team_lineup(roster, overrides[team_id])
        starters = {p.id: p for players in lineup.values() for p in players}
        record = records[team_id]
        seed = seeds.get(team_id)
        team = db.get(Team, team_id)
        finances = money.season_finances(db, season, team)
        facts[team_id] = rules.Season(
            wins=record.wins, losses=record.losses, ties=record.ties, weeks=weeks,
            playoffs=seed is not None, playoff_wins=playoff_wins[team_id],
            title=season.champion_team_id == team_id,
            division=bool(seed and seed.division_winner),
            young_starters=sum(1 for p in starters.values() if p.age <= rules.YOUNG_AGE),
            stars=sum(1 for p in roster if p.overall >= rules.STAR_OVERALL),
            ticket_price=team.ticket_price, profit=finances.profit,
            projected_profit=finances.projected_profit), finances
    return facts


def review(db: Session, season: Season) -> None:
    """Every owner reviews the season (once), when the champion is crowned."""
    rows = list(db.scalars(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                                     OwnerSeason.results.is_(None))))
    if not rows:
        return
    owners = {o.team_id: o for o in db.scalars(
        select(Owner).where(Owner.league_id == season.league_id))}
    facts = _facts(db, season, [r.team_id for r in rows])
    for row in rows:
        owner, team = owners[row.team_id], db.get(Team, row.team_id)
        fact, finances = facts[row.team_id]
        base = team.fan_mood if team.fan_mood is not None else 50
        mood = rules.fan_mood(base, fact, drift=True)
        results = [(g, bool(rules.met(g, fact, mood, final=True))) for g in _goals(row)]
        parts = rules.confidence_change(results, owner.patience, mood)
        after = rules.clamp(owner.confidence + sum(v for _, v in parts))
        row.results = [{"label": g.label, "met": done} for g, done in results]
        row.confidence_parts = [[label, value] for label, value in parts]
        row.fan_parts = [[label, value] for label, value in rules.fan_change(fact)]
        row.confidence_before, row.confidence_after = owner.confidence, after
        row.fan_mood_before, row.fan_mood_after = base, mood
        row.verdict = rules.verdict(after - owner.confidence, after)
        row.finances = finances.summary(team.ticket_price)
        owner.confidence, team.fan_mood = after, mood
    db.flush()


def unreview(db: Session, season: Season) -> None:
    """Take a season's review back (a rolled-back final): confidence and fan mood as they
    were before it."""
    owners = {o.team_id: o for o in db.scalars(
        select(Owner).where(Owner.league_id == season.league_id))}
    for row in db.scalars(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                                    OwnerSeason.results.is_not(None))):
        owners[row.team_id].confidence = row.confidence_before
        db.get(Team, row.team_id).fan_mood = row.fan_mood_before
        row.results = row.confidence_parts = row.fan_parts = row.verdict = None
        row.confidence_before = row.confidence_after = None
        row.fan_mood_before = row.fan_mood_after = None
        row.finances = None
    db.flush()


# ---------- the view ----------

def owner_view(db: Session, team: Team) -> OwnerOut:
    """A team's owner and fans: what the owner wants, this season's goals and how they're
    going, confidence and fan mood (with what moved them), and the last review."""
    league = team.league
    ensure_owners(db, league)
    owner = db.scalar(select(Owner).where(Owner.team_id == team.id))
    season = current_season(db, league.id)
    row = db.scalar(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                              OwnerSeason.team_id == team.id)) if season else None
    base = team.fan_mood if team.fan_mood is not None else 50
    mood, fan_parts, goals = base, [], []
    if row is not None:
        fact, _finances = _facts(db, season, [team.id])[team.id]
        final = row.results is not None
        if not final:
            mood = rules.fan_mood(base, fact)
            fan_parts = [[label, value] for label, value in rules.fan_change(fact)]
        for goal in _goals(row):
            done = rules.met(goal, fact, mood, final=final)
            status = ("met" if done else "missed") if done is not None else (
                "on_track" if rules.on_track(goal, fact, mood) else "behind")
            goals.append(OwnerGoalOut(label=goal.label, kind=goal.kind, status=status,
                                      primary=goal.weight == rules.PRIMARY_WEIGHT))
    last = db.scalar(select(OwnerSeason).join(Season).where(
        OwnerSeason.team_id == team.id, OwnerSeason.results.is_not(None))
        .order_by(Season.year.desc()).limit(1))
    return OwnerOut(
        team=team_summary(team), name=owner.full_name, priority=owner.priority,
        wants=rules.PRIORITIES[owner.priority], patience=owner.patience,
        confidence=owner.confidence, hot_seat=owner.confidence < rules.HOT_SEAT,
        market=team.market or "medium", fan_mood=mood, fan_parts=fan_parts,
        season_year=season.year if season else None,
        situation=row.situation if row else None, goals=goals,
        last_review=_review_out(db, last) if last else None)


def _review_out(db: Session, row: OwnerSeason) -> OwnerReviewOut:
    return OwnerReviewOut(
        year=db.get(Season, row.season_id).year, verdict=row.verdict or "",
        results=row.results or [], confidence_before=row.confidence_before,
        confidence_after=row.confidence_after, confidence_parts=row.confidence_parts or [],
        fan_mood_before=row.fan_mood_before, fan_mood_after=row.fan_mood_after,
        fan_parts=row.fan_parts or [])

