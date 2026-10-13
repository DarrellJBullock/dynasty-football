"""Players' personalities and moods (docs/design/players-and-storylines.md §3). Pure: no
database. A mood is a base carried from last season plus this season's parts, each shown
with what it's worth (pillar 3: readable depth).
"""

import random
from dataclasses import dataclass

DRIVES = {  # drive: (label, what it means)
    "competitor": ("Competitor", "wants to win"),
    "mercenary": ("Mercenary", "wants to be paid"),
    "loyal": ("Loyal", "wants to stay"),
    "steady": ("Steady", "takes things as they come"),
}
DRIVE_WEIGHTS = (30, 25, 20, 25)
TEMPERAMENTS = {  # temperament: (label, what it means)
    "leader": ("Leader", "lifts the locker room"),
    "team_player": ("Team player", "keeps an even keel"),
    "volatile": ("Volatile", "feels everything more"),
}
LEADER_CHANCE = (0.12, 0.27)  # young, then veteran (28+)
VOLATILE_CHANCE = 0.15

START_MOOD = 60  # a new player's
CARRY = 0.5  # how much of last season's mood (away from 50) carries into the next

# This season's parts.
STARTER = 5  # starting
BENCHED = -10  # a backup who could start: within this of the starter, and old enough to mind
BENCH_GAP = 3
BENCH_AGE = 24
WIN_SWING = 20  # a 1.000 season +10, a .000 season −10
DRIVE_WINNING = {"competitor": 1.5, "mercenary": 0.5}
UNDERPAID = (0.8, -8)  # paid under this share of his market price
WELL_PAID = (1.2, 3)  # ...or over this
DRIVE_MONEY = {"mercenary": 1.5, "loyal": 0.5}
CONTRACT_YEAR = -4  # the last year of the deal (not for the loyal)
TEMPER = {"volatile": 1.5, "team_player": 0.75}

LABELS = ((75, "Happy"), (55, "Content"), (35, "Unhappy"), (0, "Miserable"))


@dataclass(frozen=True)
class Traits:
    drive: str
    temperament: str


def make(rng: random.Random, age: int) -> Traits:
    drive = rng.choices(list(DRIVES), weights=DRIVE_WEIGHTS)[0]
    roll = rng.random()
    leader = LEADER_CHANCE[1] if age >= 28 else LEADER_CHANCE[0]
    temperament = ("leader" if roll < leader
                   else "volatile" if roll < leader + VOLATILE_CHANCE else "team_player")
    return Traits(drive, temperament)


def rng_for(league_id: int, player_id: int) -> random.Random:
    """A player's own stream: his traits never depend on anyone else's draws."""
    return random.Random(f"personality:{league_id}:{player_id}")


@dataclass(frozen=True)
class Situation:
    """A player's season, as his mood sees it."""
    role: str  # starter | benched | backup | free_agent
    win_pct: float | None  # the team's so far (None: no games yet, or no team)
    pay_ratio: float | None  # salary / market price (None: no contract)
    contract_year: bool


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def mood_parts(traits: Traits, situation: Situation) -> list[tuple[str, int]]:
    """What this season has done to a player's mood, part by part (temperament scales
    them all)."""
    parts: list[tuple[str, float]] = []
    if situation.role == "starter":
        parts.append(("Starting", STARTER))
    elif situation.role == "benched":
        parts.append(("Wants to start", BENCHED))
    if situation.win_pct is not None:
        parts.append(("The team's record", (situation.win_pct - 0.5) * WIN_SWING
                      * DRIVE_WINNING.get(traits.drive, 1.0)))
    if situation.pay_ratio is not None:
        money = DRIVE_MONEY.get(traits.drive, 1.0)
        if situation.pay_ratio < UNDERPAID[0]:
            parts.append(("Underpaid", UNDERPAID[1] * money))
        elif situation.pay_ratio > WELL_PAID[0]:
            parts.append(("Well paid", WELL_PAID[1] * money))
    if situation.contract_year and traits.drive != "loyal":
        parts.append(("A contract year", CONTRACT_YEAR))
    scale = TEMPER.get(traits.temperament, 1.0)
    return [(label, round(value * scale)) for label, value in parts if round(value * scale)]


def mood(base: int, parts: list[tuple[str, int]]) -> int:
    return clamp(base + sum(value for _, value in parts))


def next_base(mood_now: int) -> int:
    """Next season's starting mood: part of how this one ended."""
    return clamp(50 + (mood_now - 50) * CARRY)


def label(value: int) -> str:
    return next(name for floor, name in LABELS if value >= floor)
