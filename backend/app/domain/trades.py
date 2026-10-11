"""Trade valuation: what a player or a draft pick is worth to an AI team, and when it
says yes. Pure and deterministic.

A player's value grows steeply with OVR (one 90 is worth far more than two 70s), counts
a young player's upside, fades after 30, scales by position, and adds the surplus of his
contract (market value minus salary) over up to three seasons. A pick is worth most at
the top of the first round and falls off quickly.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.contracts import market_salary
from app.domain.positions import Position

TRADE_DEADLINE_WEEK = 10  # trades are open through this week of the regular season
AI_MARGIN = 0.05  # an AI team wants 5% more value than it gives up
NEED_BONUS = 0.15  # ...and values players at positions it needs this much more

POSITION_VALUE: dict[Position, float] = {
    Position.QB: 1.5, Position.DE: 1.15, Position.OT: 1.1, Position.CB: 1.1,
    Position.WR: 1.1, Position.RB: 0.85, Position.FB: 0.5, Position.K: 0.35,
    Position.P: 0.3,
}
CONTRACT_YEARS_COUNTED = 3

TOP_PICK_VALUE = 100.0
PICK_DECAY = 35.0  # picks lose ~1/e of their value every this many picks


def player_value(position: str, overall: int, age: int, potential: int, salary: int,
                 years_left: int) -> float:
    talent = max(0, overall - 50) ** 2 / 10
    if age <= 25:  # upside: the younger, the more of it counts
        talent += max(0, potential - overall) * (26 - age) * 0.6
    if age >= 30:
        talent *= max(0.3, 1 - 0.1 * (age - 29))
    talent *= POSITION_VALUE.get(Position(position), 1.0)
    surplus = (market_salary(Position(position), overall) - salary) / 1_000_000
    return max(0.0, talent + surplus * min(max(years_left, 0), CONTRACT_YEARS_COUNTED))


def pick_value(expected_number: int) -> float:
    return TOP_PICK_VALUE * math.exp(-(expected_number - 1) / PICK_DECAY)


@dataclass(frozen=True)
class Asset:
    value: float
    needed: bool = False  # a position the receiving team needs (AI side only)


def ai_side(received: Iterable[Asset], given: Iterable[Asset]) -> tuple[float, float]:
    """(value the AI gets, value it needs to get) for a proposal."""
    gets = sum(a.value * (1 + NEED_BONUS if a.needed else 1) for a in received)
    gives = sum(a.value for a in given)
    return gets, gives * (1 + AI_MARGIN)


def acceptable(gets: float, needs: float) -> bool:
    return gets > 0 and gets >= needs
