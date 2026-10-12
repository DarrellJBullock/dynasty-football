"""In-game injuries: who gets hurt on a snap, what it is, and how long it lasts.

Pure and deterministic: the engine passes its own injury RNG (separate from the play RNG,
so a game without injuries plays out exactly as it would without this module).
"""

import random
from collections.abc import Callable, Iterable

from app.sim.teams import SimPlayer
from app.sim.tuning import Tuning

SEASON_ENDING = 99  # weeks: out for the rest of the season (and the playoffs)

# (description, relative frequency, (min weeks, max weeks) of games missed). 0 weeks: the
# player leaves this game but is only questionable for the next one.
INJURY_TABLE: tuple[tuple[str, float, tuple[int, int]], ...] = (
    ("Ankle sprain", 18, (0, 2)),
    ("Hamstring strain", 15, (0, 3)),
    ("Knee sprain", 11, (1, 4)),
    ("Concussion", 9, (0, 2)),
    ("Shoulder sprain", 9, (0, 3)),
    ("Groin strain", 8, (0, 2)),
    ("Rib contusion", 8, (0, 1)),
    ("Back spasms", 6, (0, 1)),
    ("High ankle sprain", 6, (2, 6)),
    ("Hand fracture", 4, (2, 5)),
    ("Broken collarbone", 2, (6, 10)),
    ("Torn pectoral", 1.5, (SEASON_ENDING, SEASON_ENDING)),
    ("Torn ACL", 2.5, (SEASON_ENDING, SEASON_ENDING)),
)

# Event keys naming players in contact on a play (ball carriers, tacklers, sacked QBs).
_CONTACT = {"rush": ("player",), "scramble": ("qb",), "sack": ("qb", "by"),
            "tackle": ("by",), "fumble": ("player",), "interception": ("by",)}


def contact_ids(events: Iterable[dict]) -> set[int]:
    ids: set[int] = set()
    for event in events:
        for key in _CONTACT.get(event["t"], ()):
            value = event[key]
            ids.update(value if isinstance(value, list) else [value])
        if event["t"] == "pass" and event.get("result") == "complete":
            ids.add(event["target"])
    return ids


def _base_chance(player: SimPlayer, t: Tuning) -> float:
    toughness = player.ratings.get("toughness", 70)
    history = 1 + t.injury_history_k * min(player.injuries, t.injury_history_cap)
    return t.injury_rate * max(0.4, 1.5 - toughness / 100) * history


def injury_chance(player: SimPlayer, contact: bool, t: Tuning) -> float:
    """Per-snap chance; tougher players get hurt less, players in contact more, and
    players hurt before a little more."""
    return _base_chance(player, t) * (t.injury_contact_factor if contact else 1.0)


def roll_injuries(rng: random.Random, on_field: Iterable[SimPlayer], events: list[dict],
                  t: Tuning, cache: dict[int, float] | None = None,
                  tiredness: Callable[[int], float] | None = None) -> list[SimPlayer]:
    """The player hurt on this snap, if any (stand-ins with negative ids never are).

    One draw decides whether anyone is hurt (the chances sum to a few percent, so two on
    one snap is negligible), a second picks who, weighted by each player's chance.
    `cache` holds per-player base chances for the game; `tiredness` multiplies a player's
    chance by how tired he is (sim/fatigue.py)."""
    cache = {} if cache is None else cache
    contact = contact_ids(events)
    odds = []
    for p in on_field:
        if p.id <= 0:
            continue
        base = cache.get(p.id)
        if base is None:
            base = cache[p.id] = _base_chance(p, t)
        chance = base * t.injury_contact_factor if p.id in contact else base
        odds.append((p, chance * tiredness(p.id) if tiredness else chance))
    total = sum(chance for _, chance in odds)
    if not odds or rng.random() >= total:
        return []
    pick = rng.random() * total
    for player, chance in odds:
        pick -= chance
        if pick < 0:
            return [player]
    return [odds[-1][0]]


def injury_details(rng: random.Random) -> tuple[str, int]:
    """(description, games to miss)."""
    names, weights, ranges = zip(*INJURY_TABLE, strict=True)
    index = rng.choices(range(len(names)), weights=weights)[0]
    low, high = ranges[index]
    return names[index], rng.randint(low, high)
