"""Staff (docs/design/staff-and-legacy.md §3): the roles, how staff are made, what they're
paid, and Coach of the Year. Pure: functions take an explicit `random.Random`."""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ROLES = {  # role: (label, what they do)
    "head_coach": ("Head coach", "Runs the team: a smaller lift to every player's development."),
    "offensive_coordinator": ("Offensive coordinator", "Develops the offense's young players "
                              "and slows its veterans' decline."),
    "defensive_coordinator": ("Defensive coordinator", "Develops the defense's young players "
                              "and slows its veterans' decline."),
    "scout": ("Scout", "Sharper draft projections, and more scouting reports a class."),
    "trainer": ("Head trainer", "Injured players come back sooner."),
}
SPECIALTIES = {  # the position group a coach is best with (None: no specialty)
    "head_coach": ("offense", "defense"),
    "offensive_coordinator": ("QB", "RB", "WR", "TE", "OL"),
    "defensive_coordinator": ("DL", "LB", "DB"),
    "scout": None,
    "trainer": None,
}
AGES = {"head_coach": (38, 66), "offensive_coordinator": (32, 62),
        "defensive_coordinator": (32, 62), "scout": (28, 64), "trainer": (30, 62)}
RATING_MEAN, RATING_SD = 66, 11
RATING_MIN, RATING_MAX = 40, 99
NEUTRAL = 50  # a rating that changes nothing (part 3)

# Salary: a base by role, rising with the rating (whole dollars a season).
SALARY_BASE = {"head_coach": 3_000_000, "offensive_coordinator": 1_200_000,
               "defensive_coordinator": 1_200_000, "scout": 400_000, "trainer": 400_000}
SALARY_PER_POINT = {"head_coach": 160_000, "offensive_coordinator": 60_000,
                    "defensive_coordinator": 60_000, "scout": 20_000, "trainer": 20_000}


@dataclass(frozen=True)
class NewStaff:
    role: str
    age: int
    rating: int
    specialty: str | None
    years: int  # contract seasons left, including this one


def rating(rng: random.Random) -> int:
    return max(RATING_MIN, min(RATING_MAX, round(rng.gauss(RATING_MEAN, RATING_SD))))


def make(rng: random.Random, role: str) -> NewStaff:
    low, high = AGES[role]
    specialties = SPECIALTIES[role]
    return NewStaff(role=role, age=rng.randint(low, high), rating=rating(rng),
                    specialty=rng.choice(specialties) if specialties else None,
                    years=rng.randint(1, 4))


def salary(role: str, rating: int) -> int:
    """What a staff member at this rating earns (rounded to $10,000)."""
    raw = SALARY_BASE[role] + SALARY_PER_POINT[role] * max(0, rating - NEUTRAL)
    return round(raw, -4)


@dataclass(frozen=True)
class CoachSeason:
    staff_id: int
    wins: int
    previous_wins: int | None  # the team's wins the season before (None: no season before)


def coach_of_the_year(seasons: Sequence[CoachSeason]) -> int | None:
    """The head coach whose team improved most (wins over the season before; a first
    season counts as no change), then won most. None without coaches."""
    def key(s: CoachSeason) -> tuple[int, int, int]:
        improved = s.wins - s.previous_wins if s.previous_wins is not None else 0
        return improved, s.wins, -s.staff_id

    return max(seasons, key=key).staff_id if seasons else None


def role_label(role: str) -> str:
    return ROLES[role][0]


def describe(role: str) -> str:
    return ROLES[role][1]


def career(rows: Sequence[Mapping[str, int]]) -> dict[str, int]:
    """A staff member's seasons summed: wins, losses, ties, playoff wins, titles, awards."""
    keys = ("wins", "losses", "ties", "playoff_wins", "champion", "coach_of_the_year")
    return {k: sum(int(r[k]) for r in rows) for k in keys} | {"seasons": len(rows)}


# ---------- what staff do (part 3): off the field only; no draws of their own ----------

GROWTH_PER_POINT = 0.25 / 40  # a 90-rated coordinator: young players grow 25% faster...
SPECIALTY_BONUS = 0.10  # ...and 10% more at the position group they specialize in
HEAD_COACH_SHARE = 0.4  # the head coach's lift, as a share of a coordinator's
DECLINE_PER_POINT = 0.20 / 40  # a 90-rated coordinator: veterans decline 20% slower
FACTOR_MIN, FACTOR_MAX = 0.5, 1.6
SCOUT_SD_PER_POINT = 0.5 / 40  # a 90-rated scout: projections half as far off
SCOUT_SCALE_MIN, SCOUT_SCALE_MAX = 0.4, 1.3
REPORTS_PER_POINTS = 5  # a scouting report a class for every 5 rating points over 50
REPORTS_MIN = 10
TRAINER_PER_POINT = 0.30 / 40  # a 90-rated trainer: layoffs 30% shorter
TRAINER_SCALE_MIN, TRAINER_SCALE_MAX = 0.55, 1.2

GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "OT": "OL", "OG": "OL",
         "C": "OL", "DE": "DL", "DT": "DL", "OLB": "LB", "MLB": "LB", "CB": "DB", "FS": "DB",
         "SS": "DB"}
OFFENSE_GROUPS = {"QB", "RB", "WR", "TE", "OL"}


@dataclass(frozen=True)
class Coach:
    rating: int
    specialty: str | None = None


def side(position: str) -> str:
    """offense | defense | special (kickers and punters)."""
    group = GROUP.get(position)
    if group is None:
        return "special"
    return "offense" if group in OFFENSE_GROUPS else "defense"


def coordinator_role(position: str) -> str | None:
    return {"offense": "offensive_coordinator",
            "defense": "defensive_coordinator"}.get(side(position))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def growth_lift(position: str, coordinator: Coach | None, head: Coach | None) -> float:
    """How much faster than normal a young player grows (0.18 = 18% faster)."""
    lift = 0.0
    if coordinator is not None:
        lift += (coordinator.rating - NEUTRAL) * GROWTH_PER_POINT
        if coordinator.specialty is not None and coordinator.specialty == GROUP.get(position):
            lift += SPECIALTY_BONUS
    if head is not None:
        lift += (head.rating - NEUTRAL) * GROWTH_PER_POINT * HEAD_COACH_SHARE
        if head.specialty == side(position):
            lift += SPECIALTY_BONUS * HEAD_COACH_SHARE
    return _clamp(1 + lift, FACTOR_MIN, FACTOR_MAX) - 1


def decline_cut(coordinator: Coach | None, head: Coach | None) -> float:
    """How much slower than normal a veteran declines (0.15 = 15% slower)."""
    cut = 0.0
    if coordinator is not None:
        cut += (coordinator.rating - NEUTRAL) * DECLINE_PER_POINT
    if head is not None:
        cut += (head.rating - NEUTRAL) * DECLINE_PER_POINT * HEAD_COACH_SHARE
    return 1 - _clamp(1 - cut, FACTOR_MIN, FACTOR_MAX)


def development_factors(position: str, coordinator: Coach | None,
                        head: Coach | None) -> tuple[float, float]:
    """(growth, decline) multipliers for `development.develop` (1.0 is no staff effect)."""
    return 1 + growth_lift(position, coordinator, head), 1 - decline_cut(coordinator, head)


def scout_scale(scout: Coach | None) -> float:
    """How far off unscouted projections are, against an average scout's (1.0)."""
    if scout is None:
        return 1.0
    return _clamp(1 - (scout.rating - NEUTRAL) * SCOUT_SD_PER_POINT,
                  SCOUT_SCALE_MIN, SCOUT_SCALE_MAX)


def scouting_reports(base: int, scout: Coach | None) -> int:
    if scout is None:
        return base
    return max(REPORTS_MIN, base + (scout.rating - NEUTRAL) // REPORTS_PER_POINTS)


def layoff(weeks: int, trainer: Coach | None, season_ending: int) -> int:
    """An injury's weeks out with this trainer (season-ending injuries stay so)."""
    if trainer is None or weeks <= 1 or weeks >= season_ending:
        return weeks
    scale = _clamp(1 - (trainer.rating - NEUTRAL) * TRAINER_PER_POINT,
                   TRAINER_SCALE_MIN, TRAINER_SCALE_MAX)
    return max(1, round(weeks * scale))


def percent(value: float) -> str:
    """+0.18 -> "18%" (a whole number of percent)."""
    return f"{round(abs(value) * 100)}%"


def effect_text(role: str, rating: int, specialty: str | None) -> str:
    """What a staff member at this rating does, in a line (for the staff page)."""
    coach = Coach(rating, specialty)
    if role in ("offensive_coordinator", "defensive_coordinator"):
        lift = (rating - NEUTRAL) * GROWTH_PER_POINT
        cut = decline_cut(coach, None)
        unit = "offensive" if role == "offensive_coordinator" else "defensive"
        sign = "faster" if lift >= 0 else "slower"
        text = f"Young {unit} players grow {percent(lift)} {sign}"
        if specialty:
            text += f" ({percent(lift + SPECIALTY_BONUS)} at {specialty})"
        return text + f"; veterans decline {percent(cut)} {'slower' if cut >= 0 else 'faster'}."
    if role == "head_coach":
        lift = (rating - NEUTRAL) * GROWTH_PER_POINT * HEAD_COACH_SHARE
        return (f"Every young player grows {percent(lift)} {'faster' if lift >= 0 else 'slower'}"
                f"{f' (more on {specialty})' if specialty else ''}.")
    if role == "scout":
        scale = scout_scale(coach)
        reports = (rating - NEUTRAL) // REPORTS_PER_POINTS
        closer = "closer" if scale <= 1 else "further off"
        return (f"Draft projections {percent(1 - scale)} {closer}; "
                f"{'+' if reports >= 0 else ''}{reports} scouting reports a class.")
    scale = _clamp(1 - (rating - NEUTRAL) * TRAINER_PER_POINT, TRAINER_SCALE_MIN,
                   TRAINER_SCALE_MAX)
    return f"Injured players come back {percent(1 - scale)} {'sooner' if scale <= 1 else 'later'}."
