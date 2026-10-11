"""Offseason player development: growth toward potential, age decline, retirement.

Pure rules: every function takes the player's numbers and an explicit `random.Random`.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.positions import SPECIAL_TEAMS, Position
from app.domain.ratings import POSITION_WEIGHTS, calculate_overall, clamp_rating

# Share of the gap to potential closed in a year by a young player, by development trait.
GROWTH_RATE = {"normal": 0.30, "impact": 0.40, "star": 0.50, "elite": 0.60}
PEAK_START = 27  # growth tapers off from here...
DECLINE_START = 30  # ...and decline begins here (kickers and punters: +4 years)
DECLINE_PER_YEAR = 1.0  # OVR lost per year past DECLINE_START, growing each year
SPECIALIST_LONGEVITY = 4

PHYSICAL = ("speed", "acceleration", "agility", "stamina", "strength")
MENTAL = ("awareness", "play_recognition")

# Chance of retiring this offseason by (effective) age; 40+ always retires.
RETIREMENT_BY_AGE = {30: 0.02, 31: 0.05, 32: 0.10, 33: 0.18, 34: 0.28, 35: 0.40,
                     36: 0.55, 37: 0.70, 38: 0.80, 39: 0.90}
MANDATORY_RETIREMENT_AGE = 40
FRINGE_OVR, FRINGE_EXIT = 66, 0.5  # unsigned players below this OVR leave football at this rate


@dataclass(frozen=True)
class Development:
    ratings: dict[str, int]
    overall: int
    potential: int


def effective_age(position: str, age: int) -> int:
    """Kickers and punters age more slowly."""
    return age - SPECIALIST_LONGEVITY if Position(position) in SPECIAL_TEAMS else age


def overall_change(rng: random.Random, position: str, age: int, overall: int, potential: int,
                   trait: str) -> float:
    """Expected OVR change for a player entering the season at `age`."""
    age = effective_age(position, age)
    if age < PEAK_START:
        gap = max(0, potential - overall)
        return gap * GROWTH_RATE.get(trait, GROWTH_RATE["normal"]) * rng.uniform(0.5, 1.4)
    if age < DECLINE_START:
        return rng.gauss(0.3, 1.2)
    years_past = age - DECLINE_START + 1
    return -DECLINE_PER_YEAR * years_past * rng.uniform(0.6, 1.4)


def develop(rng: random.Random, position: str, age: int, ratings: Mapping[str, int],
            potential: int, trait: str) -> Development:
    """A year of development. Growth lifts the attributes the position values; decline
    hits physical attributes hardest while mental ones hold up."""
    overall = calculate_overall(position, ratings)
    delta = overall_change(rng, position, age, overall, potential, trait)
    weights = POSITION_WEIGHTS[Position(position)]
    new: dict[str, int] = {}
    for name, value in ratings.items():
        if delta >= 0:
            change = delta if name in weights else delta * 0.3
        elif name in PHYSICAL:
            change = delta * 1.5
        elif name in MENTAL:
            change = delta * 0.3
        else:
            change = delta * 0.8 if name in weights else delta * 0.5
        new[name] = clamp_rating(value + change + rng.gauss(0, 0.8))
    new_overall = calculate_overall(position, new)
    return Development(ratings=new, overall=new_overall, potential=max(potential, new_overall))


def retirement_chance(position: str, age: int, overall: int, signed: bool) -> float:
    age = effective_age(position, age)
    if age >= MANDATORY_RETIREMENT_AGE:
        return 1.0
    chance = RETIREMENT_BY_AGE.get(age, 0.0)
    if overall >= 80:
        chance *= 0.5
    elif overall < 65:
        chance *= 1.5
    if not signed and age >= DECLINE_START:
        chance = chance * 2 + 0.1  # unsigned veterans move on
    if not signed and overall < FRINGE_OVR:
        chance = max(chance, FRINGE_EXIT)  # so do fringe free agents of any age
    return min(1.0, chance)


def contract_years(rng: random.Random, age: int) -> int:
    """Length of a new deal: young players sign longer."""
    if age <= 26:
        return rng.randint(3, 5)
    if age <= 30:
        return rng.randint(2, 4)
    return rng.randint(1, 2)
