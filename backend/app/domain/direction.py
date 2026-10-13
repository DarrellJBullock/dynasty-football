"""An AI front office's direction (docs/design/owners-and-front-offices.md §5): contending,
in the middle, or rebuilding, decided each offseason from the roster and the owner, and
how it builds to match. Pure: no database. Every decision says why (pillar 3).
"""

from collections.abc import Sequence
from dataclasses import dataclass

DIRECTIONS = {  # direction: in words
    "contend": "Contending",
    "middle": "In the middle",
    "rebuild": "Rebuilding",
}
OLD_STARTERS = 29.0  # starters this old on average are past their best together
YOUNG_STARTERS = 26.5  # ...and this young, still to reach it

# Re-signing: a team keeps an expiring player younger than this, or at least this good.
KEEP = {"contend": (32, 68), "middle": (30, 70), "rebuild": (28, 80)}
# Free agency: a rebuilder passes on players this old, and wants a bigger upgrade.
REBUILD_MAX_AGE = 29
UPGRADE_MARGIN = {"contend": 2, "middle": 4, "rebuild": 8}
# Cap planning: contenders and the middle keep this share of next year's raises free.
EXTENSION_RESERVE = {"contend": 1.0, "middle": 0.5, "rebuild": 0.0}
# The draft: how much a prospect's potential counts against his rating now.
POTENTIAL_WEIGHT = {"contend": 0.30, "middle": 0.45, "rebuild": 0.60}


@dataclass(frozen=True)
class Decision:
    direction: str
    reasons: list[str]


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def decide(rank: int, teams: int, starter_ages: Sequence[int], priority: str) -> Decision:
    """From where the roster ranks (by team rating; 1 is best), how old its starters are,
    and what the owner wants."""
    third = round(teams / 3)
    age = sum(starter_ages) / len(starter_ages) if starter_ages else 27.0
    reasons = [f"{_ordinal(rank)} of {teams} by team rating",
               f"Starters average {age:.1f} years old"]
    if rank <= third:
        if age >= OLD_STARTERS and priority == "build":
            reasons.append("An aging roster, and the owner wants something that lasts")
            return Decision("middle", reasons)
        return Decision("contend", reasons)
    if rank > teams - third:
        if priority == "win_now":
            reasons.append("The owner won't wait for a rebuild")
            return Decision("middle", reasons)
        return Decision("rebuild", reasons)
    if priority == "win_now":
        reasons.append("The owner wants to win now")
        return Decision("contend", reasons)
    if priority == "build" and age >= YOUNG_STARTERS:
        reasons.append("The owner wants something that lasts, and the starters are no longer young")
        return Decision("rebuild", reasons)
    return Decision("middle", reasons)


def keeps(direction: str, age: int, overall: int) -> bool:
    """Re-signing: does a team going this way keep an expiring player?"""
    young, good = KEEP[direction]
    return age < young or overall >= good


def wants_free_agent(direction: str, age: int) -> bool:
    return direction != "rebuild" or age <= REBUILD_MAX_AGE


def extension_reserve(direction: str, raises: int) -> int:
    """Cap room kept for next year's extensions, from the raises they'll need."""
    return round(raises * EXTENSION_RESERVE[direction])
