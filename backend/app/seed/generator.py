"""Deterministic generator for the default fictional league.

Given the same seed, the same league, rosters, contracts, and schedule are produced.
"""

import random
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import Base
from app.domain.contracts import MIN_SALARY, market_salary
from app.domain.positions import JERSEY_RANGES, ROSTER_TEMPLATE, SPECIAL_TEAMS, Position
from app.domain.ratings import ATTRIBUTES, POSITION_WEIGHTS, calculate_overall, clamp_rating
from app.models import (
    Conference,
    Contract,
    Division,
    Franchise,
    Game,
    League,
    Player,
    PlayerRatings,
    Season,
    Team,
)
from app.schemas import ConferenceSpec, DivisionSpec, LeagueCreate, TeamIdentity
from app.seed import data

FREE_AGENT_COUNT = 64
DEFAULT_FRANCHISE_TEAM = "HFD"

# Typical (speed, strength) for each position, used for non-key attributes.
PHYSICAL_PROFILE: dict[Position, tuple[int, int]] = {
    Position.QB: (70, 60), Position.RB: (88, 68), Position.FB: (70, 80),
    Position.WR: (90, 55), Position.TE: (78, 78), Position.OT: (55, 88),
    Position.OG: (52, 90), Position.C: (52, 86), Position.DE: (78, 82),
    Position.DT: (62, 92), Position.OLB: (80, 74), Position.MLB: (76, 78),
    Position.CB: (91, 55), Position.FS: (88, 60), Position.SS: (85, 66),
    Position.K: (55, 45), Position.P: (55, 48),
}

# (min height in, max height in, min weight lb, max weight lb)
BODY: dict[Position, tuple[int, int, int, int]] = {
    Position.QB: (73, 78, 205, 240), Position.RB: (68, 73, 195, 230),
    Position.FB: (71, 74, 235, 255), Position.WR: (70, 77, 180, 220),
    Position.TE: (75, 79, 240, 265), Position.OT: (77, 81, 305, 335),
    Position.OG: (75, 78, 305, 330), Position.C: (74, 77, 295, 315),
    Position.DE: (75, 79, 250, 285), Position.DT: (74, 78, 295, 330),
    Position.OLB: (73, 77, 230, 255), Position.MLB: (72, 75, 230, 250),
    Position.CB: (69, 74, 180, 200), Position.FS: (71, 74, 195, 210),
    Position.SS: (71, 74, 200, 220), Position.K: (70, 75, 180, 210),
    Position.P: (72, 76, 195, 220),
}

DEPTH_TARGETS = (79, 70, 64)  # target OVR for starter, primary backup, depth
SPECIALIST_OFFSET = -6  # K/P have only two weighted attributes, so pull them down


def clear_database(session: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(delete(table))


def _attributes(rng: random.Random, position: Position, target: int) -> dict[str, int]:
    speed_base, strength_base = PHYSICAL_PROFILE[position]
    weights = POSITION_WEIGHTS[position]
    values: dict[str, int] = {}
    for name in ATTRIBUTES:
        if name in weights:
            base = target
        elif name in ("speed", "acceleration", "agility"):
            base = speed_base - 4
        elif name == "strength":
            base = strength_base - 4
        elif name in ("stamina", "toughness", "awareness"):
            base = target - 8
        else:
            base = rng.randint(20, 50)
        values[name] = clamp_rating(rng.gauss(base, 4))
    return values


def _development_trait(rng: random.Random, overall: int) -> str:
    roll = rng.random() + (overall - 70) / 100
    if roll > 1.05:
        return "elite"
    if roll > 0.92:
        return "star"
    if roll > 0.75:
        return "impact"
    return "normal"


def _jersey(rng: random.Random, position: Position, taken: set[int]) -> int:
    options = [n for r in JERSEY_RANGES[position] for n in r if n not in taken]
    if not options:
        options = [n for n in range(100) if n not in taken]
    number = rng.choice(options)
    taken.add(number)
    return number


def make_player(
    rng: random.Random,
    league: League,
    position: Position,
    target: int,
    team: Team | None = None,
    taken_numbers: set[int] | None = None,
) -> Player:
    attributes = _attributes(rng, position, target)
    overall = calculate_overall(position, attributes)
    age = max(21, min(36, round(rng.gauss(26, 3))))
    min_h, max_h, min_w, max_w = BODY[position]
    growth = max(0, 28 - age) * rng.uniform(0.8, 2.2)
    player = Player(
        league=league,
        team=team,
        first_name=rng.choice(data.FIRST_NAMES),
        last_name=rng.choice(data.LAST_NAMES),
        position=position.value,
        jersey_number=_jersey(rng, position, taken_numbers if taken_numbers is not None else set()),
        age=age,
        height_in=rng.randint(min_h, max_h),
        weight_lb=rng.randint(min_w, max_w),
        college=rng.choice(data.COLLEGES),
        years_pro=max(0, age - 22),
        overall=overall,
        potential=clamp_rating(overall + growth),
        development_trait=_development_trait(rng, overall),
        injury_status="healthy",
    )
    player.ratings = PlayerRatings(**attributes)
    return player


def _sign(rng: random.Random, player: Player, team: Team, year: int) -> Contract:
    contract = Contract(
        team_id=team.id,
        start_year=year - rng.randint(0, 2),
        years=rng.randint(1, 5),
        salary=market_salary(Position(player.position), player.overall),
        signing_bonus=0,
        is_active=True,
    )
    if contract.end_year < year:
        contract.years = year - contract.start_year + 1
    player.contracts.append(contract)
    return contract


def _fit_under_cap(contracts: list[Contract], cap: int, ceiling: float = 0.94) -> None:
    payroll = sum(c.salary for c in contracts)
    limit = int(cap * ceiling)
    if payroll <= limit:
        return
    excess_total = sum(c.salary - MIN_SALARY for c in contracts)
    scale = (limit - MIN_SALARY * len(contracts)) / excess_total
    for c in contracts:
        c.salary = int(round(MIN_SALARY + (c.salary - MIN_SALARY) * scale, -4))


def round_robin(team_ids: list[int], rounds: int) -> list[list[tuple[int, int]]]:
    """Circle-method round robin. Returns `rounds` weeks of (home, away) pairs.

    Each opponent is met once per n-1 weeks; small leagues with more weeks than that
    cycle through the rotation again. Home field goes to whichever team has hosted
    fewer games so far (ties go to the team that was away most recently), which keeps
    every team within one home game of an even split.
    """
    ids = list(team_ids)
    if len(ids) % 2:
        raise ValueError("round_robin requires an even number of teams")
    n = len(ids)
    home_games = dict.fromkeys(ids, 0)
    last_home = dict.fromkeys(ids, False)
    weeks: list[list[tuple[int, int]]] = []
    for _ in range(rounds):
        pairs = []
        for i in range(n // 2):
            a, b = ids[i], ids[n - 1 - i]
            a_hosts = (home_games[a], last_home[a]) <= (home_games[b], last_home[b])
            home, away = (a, b) if a_hosts else (b, a)
            home_games[home] += 1
            last_home[home], last_home[away] = True, False
            pairs.append((home, away))
        weeks.append(pairs)
        ids = [ids[0], ids[-1], *ids[1:-1]]
    return weeks


def default_spec() -> LeagueCreate:
    """The shipped Dynasty Football League as a league spec."""
    conferences = [
        ConferenceSpec(name=conf_name, abbreviation=conf_abbr, divisions=[
            DivisionSpec(name=f"{conf_abbr} {div_name}",
                         teams=[_identity(team) for team in team_defs])
            for div_name, team_defs in divisions.items()
        ])
        for (conf_name, conf_abbr), divisions in data.CONFERENCES.items()
    ]
    return LeagueCreate(name=data.LEAGUE_NAME, abbreviation=data.LEAGUE_ABBREVIATION,
                        salary_cap=data.SALARY_CAP, season_year=data.START_YEAR,
                        weeks=data.REGULAR_SEASON_WEEKS, conferences=conferences,
                        user_team=DEFAULT_FRANCHISE_TEAM)


def league_template(conferences: int, divisions: int, teams_per_division: int) -> LeagueCreate:
    """A ready-to-edit custom league filled from the fictional team pool."""
    total = conferences * divisions * teams_per_division
    if not 1 <= conferences <= len(data.CONFERENCE_NAMES):
        raise ValueError(f"conferences must be 1-{len(data.CONFERENCE_NAMES)}")
    if not 1 <= divisions <= len(data.DIVISION_NAMES):
        raise ValueError(f"divisions must be 1-{len(data.DIVISION_NAMES)}")
    if total > len(data.TEAM_POOL):
        raise ValueError(f"at most {len(data.TEAM_POOL)} teams")
    pool = iter(data.TEAM_POOL)
    specs = []
    for conf_name, conf_abbr in data.CONFERENCE_NAMES[:conferences]:
        div_specs = []
        for div_name in data.DIVISION_NAMES[:divisions]:
            name = f"{conf_abbr} {div_name}" if conferences > 1 or divisions > 1 else conf_name
            div_specs.append(DivisionSpec(
                name=name, teams=[_identity(next(pool)) for _ in range(teams_per_division)]))
        specs.append(ConferenceSpec(name=conf_name, abbreviation=conf_abbr, divisions=div_specs))
    first = specs[0].divisions[0].teams[0].abbreviation
    return LeagueCreate(name="Custom League", abbreviation="CUST", conferences=specs,
                        user_team=first)


def _identity(team: data.TeamDef) -> TeamIdentity:
    city, nickname, abbr, primary, secondary, stadium = team
    return TeamIdentity(city=city, nickname=nickname, abbreviation=abbr,
                        primary_color=primary, secondary_color=secondary, stadium=stadium)


def generate_league(session: Session, seed: int = 2026) -> League:
    return build_league(session, default_spec(), seed).league


def build_league(session: Session, spec: LeagueCreate, seed: int) -> Franchise:
    """Create a league from a spec: structure, rosters, free agents, schedule, and the
    user's franchise (activated). Deterministic for a given spec and seed."""
    rng = random.Random(seed)
    league = League(name=spec.name, abbreviation=spec.abbreviation.upper(),
                    salary_cap=spec.salary_cap)
    session.add(league)

    teams: list[Team] = []
    for conf_spec in spec.conferences:
        conference = Conference(name=conf_spec.name, abbreviation=conf_spec.abbreviation)
        league.conferences.append(conference)
        for div_spec in conf_spec.divisions:
            division = Division(name=div_spec.name)
            conference.divisions.append(division)
            for identity in div_spec.teams:
                team = Team(league=league, **identity.model_dump())
                division.teams.append(team)
                teams.append(team)
    session.flush()

    year = spec.season_year
    if spec.rosters == "generated":
        for team in teams:
            _populate_roster(session, rng, league, team, year)

    positions = list(ROSTER_TEMPLATE)
    position_weights = list(ROSTER_TEMPLATE.values())
    for _ in range(FREE_AGENT_COUNT):
        position = rng.choices(positions, weights=position_weights)[0]
        session.add(make_player(rng, league, position, round(rng.gauss(62, 5))))

    season = Season(league=league, year=year, phase="preseason", current_week=1)
    session.add(season)
    _schedule(session, season, [t.id for t in teams], rng, spec.weeks)

    user_team = next(t for t in teams if t.abbreviation == spec.user_team)
    franchise = Franchise(name=spec.franchise_name or f"{user_team.nickname} Dynasty",
                          league=league, team=user_team, activated_at=datetime.now(UTC))
    session.add(franchise)
    session.flush()
    return franchise


def _populate_roster(session: Session, rng: random.Random, league: League, team: Team,
                     year: int) -> None:
    quality = rng.gauss(0, 3)
    taken: set[int] = set()
    contracts: list[Contract] = []
    for position, count in ROSTER_TEMPLATE.items():
        for depth in range(count):
            target = DEPTH_TARGETS[min(depth, len(DEPTH_TARGETS) - 1)] + quality
            if position in SPECIAL_TEAMS:
                target += SPECIALIST_OFFSET
            target = rng.gauss(target, 3.5)
            player = make_player(rng, league, position, round(target), team, taken)
            session.add(player)
            contracts.append(_sign(rng, player, team, year))
    _fit_under_cap(contracts, league.salary_cap)


def _schedule(session: Session, season: Season, team_ids: Iterable[int], rng: random.Random,
              weeks: int) -> None:
    ids = list(team_ids)
    rng.shuffle(ids)
    for week_number, pairs in enumerate(round_robin(ids, weeks), start=1):
        for home, away in pairs:
            session.add(Game(season=season, week=week_number,
                             home_team_id=home, away_team_id=away))
