"""Depth chart rules: slot ordering and starting lineup selection.

Works on anything shaped like a player (id, position, overall, injury_status), so it
stays free of the ORM and is easy to unit-test.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, Protocol

from app.domain.positions import DEFENSE, OFFENSE, STARTERS, Position

UNAVAILABLE = frozenset({"out", "injured_reserve"})

Unit = Literal["offense", "defense", "special_teams"]

# Slots in display / lineup-selection order: offense, defense, specialists.
SLOTS: tuple[Position, ...] = tuple(Position)


class PlayerLike(Protocol):
    id: int
    position: str
    overall: int
    injury_status: str


def unit_of(slot: Position) -> Unit:
    if slot in OFFENSE:
        return "offense"
    if slot in DEFENSE:
        return "defense"
    return "special_teams"


def starter_count(slot: Position) -> int:
    return STARTERS.get(slot, 0)


def is_available(player: PlayerLike) -> bool:
    return player.injury_status not in UNAVAILABLE


def build_chart[P: PlayerLike](
    players: Iterable[P], overrides: Mapping[Position, Sequence[int]] | None = None
) -> dict[Position, list[P]]:
    """Ordered players for every slot.

    A customized slot keeps its saved order (minus anyone no longer on the roster);
    players whose natural position is the slot but who are missing from it are
    appended by OVR, so new signings always appear. Uncustomized slots are by OVR.
    """
    overrides = overrides or {}
    roster = list(players)
    by_id = {p.id: p for p in roster}
    chart: dict[Position, list[P]] = {}
    for slot in SLOTS:
        ordered = [by_id[pid] for pid in overrides.get(slot, ()) if pid in by_id]
        listed = {p.id for p in ordered}
        natural = sorted(
            (p for p in roster if p.position == slot and p.id not in listed),
            key=lambda p: (-p.overall, p.id),
        )
        chart[slot] = ordered + natural
    return chart


def starting_lineup[P: PlayerLike](
    chart: Mapping[Position, Sequence[P]],
) -> dict[Position, list[P]]:
    """First available players at each starting slot, top of the chart first.

    Injured (out / IR) players are skipped, and a player starts at most once: slots
    are filled in SLOTS order, so a player listed first at two slots starts at the
    earlier one and the later slot falls through to its next player.
    """
    used: set[int] = set()
    lineup: dict[Position, list[P]] = {}
    for slot in SLOTS:
        needed = starter_count(slot)
        starters: list[P] = []
        for player in chart.get(slot, ()):
            if len(starters) == needed:
                break
            if player.id not in used and is_available(player):
                starters.append(player)
                used.add(player.id)
        lineup[slot] = starters
    return lineup
