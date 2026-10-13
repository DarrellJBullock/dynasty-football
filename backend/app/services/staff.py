"""Staff (docs/design/staff-and-legacy.md §3): every team's head coach, coordinators, scout
and trainer, their careers, and Coach of the Year.

Staff are made once per league (`ensure_staff`) from their own `random.Random`, never the
league generator's, so a league's players are the same with or without them. Each season,
when the champion is crowned (`record_season`), every staff member's season is written,
and the head coach whose team improved most is Coach of the Year.
"""

import random

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.domain.development import DECLINE_START, PEAK_START, effective_age
from app.models import Game, League, Player, Season, StaffMember, StaffSeason, Team
from app.schemas import (
    CoachesOut,
    CoachingItem,
    CoachOfTheYear,
    PlayerCoachingOut,
    StaffCareer,
    StaffOut,
    TeamStaffOut,
)
from app.seed import data
from app.services.serializers import team_summary
from app.services.standings import compute_records
from app.services.teams import current_season


def _rng(league: League) -> random.Random:
    return random.Random(f"staff:{league.id}")


def ensure_staff(db: Session, league: League) -> None:
    """Give every team a staff, once (a league from before staff gets one now). The league's
    row is locked first, so two requests at once can't both make one."""
    if db.scalar(select(StaffMember.id).where(StaffMember.league_id == league.id).limit(1)):
        return
    db.execute(select(League.id).where(League.id == league.id).with_for_update())
    if db.scalar(select(StaffMember.id).where(StaffMember.league_id == league.id).limit(1)):
        return  # (another request made them while this one waited)
    season = current_season(db, league.id)
    year = season.year if season else 0
    rng = _rng(league)
    first = data.FIRST_NAMES_WOMEN if league.players == "women" else data.FIRST_NAMES
    for team in sorted(league.teams, key=lambda t: t.id):
        for role in rules.ROLES:
            made = rules.make(rng, role)
            db.add(StaffMember(league_id=league.id, team_id=team.id, role=role,
                               first_name=rng.choice(first), last_name=rng.choice(data.LAST_NAMES),
                               age=made.age, rating=made.rating, specialty=made.specialty,
                               salary=rules.salary(role, made.rating),
                               contract_end=year + made.years - 1))
    db.flush()


def record_season(db: Session, season: Season) -> None:
    """Write every staff member's season (once, when the champion is crowned), and name
    Coach of the Year."""
    if not season.champion_team_id or db.scalar(
            select(StaffSeason.id).where(StaffSeason.season_id == season.id).limit(1)):
        return
    league = db.get(League, season.league_id)
    ensure_staff(db, league)
    team_ids = [t.id for t in league.teams]
    records = compute_records(db, season, team_ids)
    before = db.scalar(select(Season).where(Season.league_id == league.id,
                                            Season.year == season.year - 1))
    previous = compute_records(db, before, team_ids) if before else {}
    playoff_wins: dict[int, int] = {}
    for game in db.scalars(select(Game).where(Game.season_id == season.id,
                                              Game.stage == "playoff", Game.status == "final")):
        winner = (game.home_team_id if (game.home_score or 0) > (game.away_score or 0)
                  else game.away_team_id)
        playoff_wins[winner] = playoff_wins.get(winner, 0) + 1
    rows = []
    for member in db.scalars(select(StaffMember).where(StaffMember.league_id == league.id,
                                                       StaffMember.team_id.in_(team_ids))):
        record = records[member.team_id]
        row = StaffSeason(staff_id=member.id, season_id=season.id, team_id=member.team_id,
                          role=member.role, wins=record.wins, losses=record.losses,
                          ties=record.ties, playoff_wins=playoff_wins.get(member.team_id, 0),
                          champion=member.team_id == season.champion_team_id)
        db.add(row)
        rows.append(row)
    coaches = [rules.CoachSeason(r.staff_id, r.wins,
                                 previous[r.team_id].wins if r.team_id in previous else None)
               for r in rows if r.role == "head_coach"]
    winner = rules.coach_of_the_year(coaches)
    for row in rows:
        row.coach_of_the_year = row.staff_id == winner and row.role == "head_coach"
    db.flush()


def age_staff(db: Session, league: League) -> None:
    """A year older (the offseason)."""
    for member in db.scalars(select(StaffMember).where(StaffMember.league_id == league.id,
                                                       StaffMember.retired_year.is_(None))):
        member.age += 1
    db.flush()


def by_team(db: Session, league: League) -> dict[int, dict[str, StaffMember]]:
    """team id -> role -> its staff member (made first, if the league has none yet)."""
    ensure_staff(db, league)
    crew: dict[int, dict[str, StaffMember]] = {}
    for member in db.scalars(select(StaffMember).where(StaffMember.league_id == league.id,
                                                       StaffMember.team_id.is_not(None))):
        crew.setdefault(member.team_id, {})[member.role] = member
    return crew


def coach(member: StaffMember | None) -> rules.Coach | None:
    return rules.Coach(member.rating, member.specialty) if member is not None else None


def development_factors(crew: dict[int, dict[str, StaffMember]],
                        player: Player) -> tuple[float, float]:
    """(growth, decline) for a player's offseason: his team's coordinator and head coach
    (a player without a team develops on his own)."""
    if player.team_id is None or player.team_id not in crew:
        return 1.0, 1.0
    team = crew[player.team_id]
    role = rules.coordinator_role(player.position)
    return rules.development_factors(player.position, coach(team.get(role)) if role else None,
                                     coach(team.get("head_coach")))


def player_coaching(db: Session, player: Player) -> PlayerCoachingOut:
    """What his team's staff do for this player, in his terms: how fast he grows (or how
    slowly he declines) this offseason, and how soon he'd be back from an injury."""
    if player.team_id is None or player.retired_year is not None:
        return PlayerCoachingOut(items=[], phase=None)
    crew = by_team(db, db.get(League, player.league_id)).get(player.team_id, {})
    role = rules.coordinator_role(player.position)
    coordinator, head = crew.get(role) if role else None, crew.get("head_coach")
    age = effective_age(player.position, player.age + 1)  # (his age next offseason)
    phase = "growing" if age < PEAK_START else "declining" if age >= DECLINE_START else "peak"
    items = []
    if phase == "growing":
        lift = rules.growth_lift(player.position, coach(coordinator), coach(head))
        verb = f"grows {rules.percent(lift)} {'faster' if lift >= 0 else 'slower'}"
    elif phase == "declining":
        cut = rules.decline_cut(coach(coordinator), coach(head))
        verb = f"declines {rules.percent(cut)} {'slower' if cut >= 0 else 'faster'}"
    else:
        verb = None
    for member in (coordinator, head):
        if member is not None:
            items.append(CoachingItem(role=member.role, role_label=rules.role_label(member.role),
                                      name=member.full_name, rating=member.rating,
                                      specialty=member.specialty))
    trainer = crew.get("trainer")
    if trainer is not None:
        items.append(CoachingItem(role="trainer", role_label=rules.role_label("trainer"),
                                  name=trainer.full_name, rating=trainer.rating, specialty=None))
    trainer_text = rules.effect_text("trainer", trainer.rating, None) if trainer else None
    summary = (f"With these coaches he {verb} this offseason than he would on his own."
               if verb else "At his peak: his coaches' growth and decline don't apply yet.")
    return PlayerCoachingOut(items=items, phase=phase, development=summary, injuries=trainer_text)


# ---------- views ----------

def _careers(db: Session, ids: list[int]) -> dict[int, StaffCareer]:
    sums = db.execute(select(
        StaffSeason.staff_id, func.count(StaffSeason.id), func.sum(StaffSeason.wins),
        func.sum(StaffSeason.losses), func.sum(StaffSeason.ties),
        func.sum(StaffSeason.playoff_wins),
        func.sum(func.cast(StaffSeason.champion, Integer())),
        func.sum(func.cast(StaffSeason.coach_of_the_year, Integer())))
        .where(StaffSeason.staff_id.in_(ids)).group_by(StaffSeason.staff_id)).all()
    out = {i: StaffCareer() for i in ids}
    for sid, seasons, w, lo, t, pw, titles, coy in sums:
        out[sid] = StaffCareer(seasons=seasons, wins=w or 0, losses=lo or 0, ties=t or 0,
                               playoff_wins=pw or 0, titles=titles or 0,
                               coach_of_the_year=coy or 0)
    return out


def _out(member: StaffMember, career: StaffCareer, team: Team | None) -> StaffOut:
    return StaffOut(id=member.id, role=member.role, role_label=rules.role_label(member.role),
                    duty=rules.describe(member.role), name=member.full_name, age=member.age,
                    rating=member.rating, specialty=member.specialty, salary=member.salary,
                    effect=rules.effect_text(member.role, member.rating, member.specialty),
                    contract_end=member.contract_end,
                    team=team_summary(team) if team else None, career=career)


def team_staff(db: Session, team: Team) -> TeamStaffOut:
    ensure_staff(db, db.get(League, team.league_id))
    order = list(rules.ROLES)
    members = sorted(db.scalars(select(StaffMember).where(StaffMember.team_id == team.id,
                                                          StaffMember.retired_year.is_(None))),
                     key=lambda m: (order.index(m.role), m.id))
    careers = _careers(db, [m.id for m in members])
    return TeamStaffOut(team=team_summary(team),
                        members=[_out(m, careers[m.id], team) for m in members],
                        payroll=sum(m.salary for m in members))


def coaches(db: Session, league: League) -> CoachesOut:
    """Every team's head coach, and Coach of the Year by season."""
    ensure_staff(db, league)
    teams = {t.id: t for t in league.teams}
    heads = db.scalars(select(StaffMember).where(StaffMember.league_id == league.id,
                                                 StaffMember.role == "head_coach",
                                                 StaffMember.team_id.is_not(None))).all()
    careers = _careers(db, [h.id for h in heads])
    awards = db.execute(
        select(Season.year, StaffSeason, StaffMember)
        .join(Season, Season.id == StaffSeason.season_id)
        .join(StaffMember, StaffMember.id == StaffSeason.staff_id)
        .where(Season.league_id == league.id, StaffSeason.coach_of_the_year)
        .order_by(Season.year.desc())).all()
    heads = sorted(heads, key=lambda h: (-careers[h.id].wins, h.id))
    return CoachesOut(
        head_coaches=[_out(h, careers[h.id], teams.get(h.team_id)) for h in heads],
        coach_of_the_year=[CoachOfTheYear(
            year=year, staff_id=member.id, name=member.full_name,
            team=team_summary(teams[row.team_id]), wins=row.wins, losses=row.losses,
            ties=row.ties) for year, row, member in awards])
