"""The coaching carousel and the staff budget (docs/design/staff-and-legacy.md §3).

Each team spends from a staff budget (the league's setting, the same for every team) on
its staff's salaries and on dead money for staff it fired. Each offseason (`offseason`,
from offseason.advance): staff retire, contracts end, AI teams re-sign the good ones, fire
head coaches after a bad season and hire the best they can afford from a market that new
staff join. A member's team decides its own (`hire`, `fire`, `extend`); its vacancies are
filled with an interim hire when the preseason opens (`fill_vacancies`). On autopilot (sim
ahead) the member's team is run like an AI team's.
"""

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.models import Facility, League, Season, StaffDeadMoney, StaffMember, StaffSeason, Team
from app.schemas import StaffBudget, StaffMarketOut
from app.seed import data
from app.services.errors import RosterError
from app.services.members import human_team_ids
from app.services.notifications import notify_team
from app.services.standings import compute_records
from app.services.teams import current_season

YEARS_MIN, YEARS_MAX = 1, 5  # a contract a manager offers


def _rng(league: League, year: int, what: str) -> random.Random:
    return random.Random(f"carousel:{what}:{league.id}:{year}")


# ---------- the budget ----------

def dead_money(db: Session, team_id: int, year: int) -> int:
    return db.scalar(select(func.sum(StaffDeadMoney.amount)).where(
        StaffDeadMoney.team_id == team_id, StaffDeadMoney.year == year)) or 0


def facilities_cost(db: Session, team_id: int, year: int) -> int:
    """Its facilities' upkeep, and upgrades bought in `year`."""
    total = 0
    for level, upgrade_year, cost in db.execute(select(
            Facility.level, Facility.upgrade_year, Facility.upgrade_cost)
            .where(Facility.team_id == team_id)):
        total += rules.upkeep(level) + (cost if upgrade_year == year else 0)
    return total


def payroll(db: Session, team_id: int, year: int) -> int:
    """What the team's staff cost in `year`: salaries of those under contract then, dead
    money, and its facilities (services/facilities.py)."""
    salaries = db.scalar(select(func.sum(StaffMember.salary)).where(
        StaffMember.team_id == team_id, StaffMember.contract_end >= year)) or 0
    return salaries + dead_money(db, team_id, year) + facilities_cost(db, team_id, year)


def budget(db: Session, team: Team, year: int) -> StaffBudget:
    league = db.get(League, team.league_id)
    spent = payroll(db, team.id, year)
    return StaffBudget(year=year, budget=league.staff_budget, payroll=spent,
                       dead_money=dead_money(db, team.id, year),
                       room=league.staff_budget - spent)


def _year(db: Session, league_id: int) -> int:
    season = current_season(db, league_id)
    return season.year if season else 0


# ---------- a manager's moves ----------

def _vacant(db: Session, team_id: int, role: str) -> bool:
    return db.scalar(select(StaffMember.id).where(StaffMember.team_id == team_id,
                                                  StaffMember.role == role)) is None


def hire(db: Session, team: Team, staff_id: int, years: int) -> StaffMember:
    """Hire someone off the market into an open job, for `years` seasons from this one."""
    member = db.get(StaffMember, staff_id)
    if (member is None or member.league_id != team.league_id or member.team_id is not None
            or member.retired_year is not None):
        raise RosterError("They aren't on the market.")
    if not YEARS_MIN <= years <= YEARS_MAX:
        raise RosterError(f"A contract runs {YEARS_MIN} to {YEARS_MAX} seasons.", 422)
    label = rules.role_label(member.role).lower()
    if not _vacant(db, team.id, member.role):
        raise RosterError(f"The {team.nickname} already have a {label}: let them go first.")
    year = _year(db, team.league_id)
    salary = rules.salary(member.role, member.rating)
    room = budget(db, team, year).room
    if salary > room:
        raise RosterError(f"Their salary (${salary:,}) is more than your staff budget's room "
                          f"(${room:,}).")
    member.team_id, member.salary, member.contract_end = team.id, salary, year + years - 1
    db.flush()
    return member


def fire(db: Session, member: StaffMember) -> None:
    """Let them go: the team still owes their salary for every season left, as dead money."""
    if member.team_id is None:
        raise RosterError("They aren't on a team.")
    year = _year(db, member.league_id)
    for owed in range(year, member.contract_end + 1):
        db.add(StaffDeadMoney(team_id=member.team_id, staff_id=member.id, year=owed,
                              amount=member.salary))
    member.team_id = None
    db.flush()


def extend(db: Session, member: StaffMember, years: int) -> StaffMember:
    """Keep them on: a new contract from next season, at their rating's salary."""
    if member.team_id is None:
        raise RosterError("They aren't on a team.")
    year = _year(db, member.league_id)
    if member.contract_end > year:
        raise RosterError("Their contract has more than this season to run: extend it in its "
                          "final season.")
    if not YEARS_MIN <= years <= YEARS_MAX:
        raise RosterError(f"A contract runs {YEARS_MIN} to {YEARS_MAX} seasons.", 422)
    team = db.get(Team, member.team_id)
    salary = rules.salary(member.role, member.rating)
    next_year = budget(db, team, year + 1)
    if next_year.payroll + salary > next_year.budget:
        raise RosterError(f"Next season's staff budget can't fit their salary (${salary:,}).")
    member.salary, member.contract_end = salary, year + years
    db.flush()
    return member


# ---------- the offseason ----------

def offseason(db: Session, league: League, season: Season, autopilot: bool = False) -> None:
    """The carousel after `season`: retirements, firings, contracts that end, new staff on
    the market, and AI teams' hires."""
    year = season.year  # (the season just played; the next one is year + 1)
    humans = set() if autopilot else human_team_ids(db, league.id)
    teams = sorted(league.teams, key=lambda t: t.id)
    staff = list(db.scalars(select(StaffMember).where(StaffMember.league_id == league.id,
                                                      StaffMember.retired_year.is_(None))
                            .order_by(StaffMember.id)))
    rng = _rng(league, year, "offseason")
    # 1. Retirements (everyone draws, in id order, so the order is stable).
    for member in staff:
        if rng.random() < rules.retire_chance(member.age):
            if member.team_id in humans:
                notify_team(db, member.team_id, "staff",
                            f"{rules.role_label(member.role)} {member.full_name} retired",
                            "Hire a replacement on the Staff page.", "/staff",
                            key=f"staff-retired:{member.id}")
            member.retired_year, member.team_id = year, None
    db.flush()  # (the app's sessions don't autoflush: the queries below must see them gone)
    # 2. AI teams fire head coaches after a bad season (not in their first).
    records = compute_records(db, season, [t.id for t in teams])
    for team in teams:
        if team.id in humans:
            continue
        head = db.scalar(select(StaffMember).where(StaffMember.team_id == team.id,
                                                   StaffMember.role == "head_coach"))
        if (head is None or head.team_id != team.id
                or records[team.id].win_pct >= rules.FIRE_WIN_PCT):
            continue  # (no head coach, one who just retired, or a good season)
        seasons_here = db.scalar(select(func.count(StaffSeason.id)).where(
            StaffSeason.staff_id == head.id, StaffSeason.team_id == team.id)) or 0
        if seasons_here >= 2:
            _fire_after(db, head, year)
    # 3. Contracts that end: AI teams keep the good ones; members' teams already chose.
    for member in db.scalars(select(StaffMember).where(
            StaffMember.league_id == league.id, StaffMember.team_id.is_not(None),
            StaffMember.contract_end <= year).order_by(StaffMember.id)).all():
        if member.team_id not in humans and rules.ai_keeps(member.rating, member.age):
            member.salary = rules.salary(member.role, member.rating)
            member.contract_end = year + rng.randint(2, 4)
            continue
        if member.team_id in humans:
            notify_team(db, member.team_id, "staff",
                        f"{rules.role_label(member.role)} {member.full_name}'s contract ended",
                        "Hire a replacement on the Staff page.", "/staff",
                        key=f"staff-left:{member.id}:{year}")
        member.team_id = None
    # 4. New staff join the market.
    _newcomers(db, league, year)
    # 5. AI teams fill their jobs, and build with what's left; anyone over budget lets
    # facilities slip.
    from app.services import facilities  # (it builds on the budget here)

    ai_teams = [t for t in teams if t.id not in humans]
    fill_vacancies(db, league, year + 1, only=ai_teams)
    facilities.ai_upgrades(db, league, year + 1, ai_teams)
    facilities.keep_up(db, league, year + 1)
    db.flush()


def _fire_after(db: Session, head: StaffMember, year: int) -> None:
    """An AI team's firing after the season: the seasons left on the contract are owed."""
    for owed in range(year + 1, head.contract_end + 1):
        db.add(StaffDeadMoney(team_id=head.team_id, staff_id=head.id, year=owed,
                              amount=head.salary))
    head.team_id = None


def _newcomers(db: Session, league: League, year: int) -> None:
    rng = _rng(league, year, "newcomers")
    first = data.FIRST_NAMES_WOMEN if league.players == "women" else data.FIRST_NAMES
    count = max(2, len(league.teams) // rules.NEW_PER_ROLE_DIVISOR)
    for role in rules.ROLES:
        for _ in range(count):
            made = rules.make_new(rng, role)
            db.add(StaffMember(league_id=league.id, team_id=None, role=role,
                               first_name=rng.choice(first), last_name=rng.choice(data.LAST_NAMES),
                               age=made.age, rating=made.rating, specialty=made.specialty,
                               salary=rules.salary(role, made.rating), contract_end=year))
    db.flush()


def fill_vacancies(db: Session, league: League, year: int,
                   only: list[Team] | None = None) -> list[StaffMember]:
    """Hire the best affordable staff for every open job (of `only`'s teams), in team
    order. Returns the hires. A member's team (at the preseason) gets an interim hire."""
    teams = only if only is not None else sorted(league.teams, key=lambda t: t.id)
    rng = _rng(league, year, "hires")
    humans = human_team_ids(db, league.id)
    hired = []
    for team in teams:
        for role in rules.ROLES:
            if not _vacant(db, team.id, role):
                continue
            pool = [(m.id, m.rating, m.age, rules.salary(role, m.rating))
                    for m in db.scalars(select(StaffMember).where(
                        StaffMember.league_id == league.id, StaffMember.team_id.is_(None),
                        StaffMember.retired_year.is_(None), StaffMember.role == role))]
            choice = rules.best_hire(pool, budget(db, team, year).room)
            if choice is None:
                continue
            member = db.get(StaffMember, choice)
            member.team_id, member.salary = team.id, rules.salary(role, member.rating)
            member.contract_end = year + rng.randint(1, 3) - 1
            db.flush()
            hired.append(member)
            if team.id in humans and only is None:
                notify_team(db, team.id, "staff",
                            f"{member.full_name} is your interim {rules.role_label(role).lower()}",
                            "The job was open when the preseason began.", "/staff",
                            key=f"staff-interim:{member.id}:{year}")
    return hired


# ---------- the market ----------

def market(db: Session, league: League, team: Team | None) -> StaffMarketOut:
    """Staff out of work, by role then rating, and the viewer's team's budget."""
    from app.services.staff import _careers, _out  # (staff builds on the season services)

    year = _year(db, league.id)
    free = db.scalars(select(StaffMember).where(
        StaffMember.league_id == league.id, StaffMember.team_id.is_(None),
        StaffMember.retired_year.is_(None))).all()
    order = list(rules.ROLES)
    free = sorted(free, key=lambda m: (order.index(m.role), -m.rating, m.id))
    careers = _careers(db, [m.id for m in free])
    rows = []
    for m in free:
        row = _out(m, careers[m.id], None)
        row.salary = rules.salary(m.role, m.rating)  # (what they'd sign for)
        rows.append(row)
    return StaffMarketOut(year=year, candidates=rows,
                          budget=budget(db, team, year) if team else None)
