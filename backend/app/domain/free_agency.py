"""Free agency market rules: how picky players are each day and how they rank offers.

A free agent's *price* for a deal is `required_salary` for its length (market value plus a
premium for lengths he doesn't want). Early in the market he holds out for more than his
price; by the last day he'll take less. Among acceptable offers he takes the best one,
leaning slightly toward stronger teams.
"""

from collections.abc import Sequence
from dataclasses import dataclass

MARKET_DAYS = 5
# Share of his price a player needs to sign on each market day.
DEMAND = (1.15, 1.08, 1.0, 0.92, 0.80)
WINNER_PULL = 0.01  # per OVR point of team strength above/below an average team
AVERAGE_TEAM = 76

assert len(DEMAND) == MARKET_DAYS


def demand(day: int) -> float:
    return DEMAND[max(1, min(day, MARKET_DAYS)) - 1]


@dataclass(frozen=True)
class Bid:
    offer_id: int
    salary: int
    price: int  # the player's price for this offer's length
    team_overall: int

    @property
    def ratio(self) -> float:
        return self.salary / self.price

    @property
    def score(self) -> float:
        """Money first; a contender's offer counts a little more."""
        return self.ratio * (1 + WINNER_PULL * (self.team_overall - AVERAGE_TEAM))


def ranked(bids: Sequence[Bid]) -> list[Bid]:
    """Best first (earlier offers win ties)."""
    return sorted(bids, key=lambda b: (-b.score, b.offer_id))


def acceptable(bid: Bid, day: int) -> bool:
    return bid.ratio >= demand(day)
