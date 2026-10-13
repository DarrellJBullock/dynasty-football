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
