"""A team's money (docs/design/owners-and-front-offices.md §3): what a season brings in and
costs. Pure: no database. Revenue is scaled to the league's salary cap, so a league with a
custom cap keeps the same balance. Money never limits spending: the cap and the staff budget
do. It's what the owner (and a profit-minded one most of all) judges the season by.
"""

from dataclasses import dataclass

TICKET_PRICES = ("low", "normal", "high")
PRICE_LABELS = {"low": "Low", "normal": "Normal", "high": "High"}
CAPACITY = {"small": 60_000, "medium": 68_000, "large": 75_000}  # seats
# A normal ticket, by market, for a league with a $255M cap (scaled to the league's).
TICKET = {"small": 90, "medium": 110, "large": 130}
REFERENCE_CAP = 255_000_000
PRICE_FACTOR = {"low": 0.8, "normal": 1.0, "high": 1.25}
PRICE_ATTENDANCE = {"low": 0.08, "normal": 0.0, "high": -0.10}  # share of seats
PRICE_FAN_MOOD = {"low": 3, "normal": 0, "high": -3}  # a season of them
PLAYOFF_GATE = 1.5  # a home playoff game sells at this times the price

MEDIA_SHARE = 1.0  # each team's share of the media money: the salary cap, a season
MERCH_BASE = 0.03  # merchandise: 3% of the cap a season...
MERCH_PER_STAR = 0.005  # ...0.5% more for each star (up to 5)...
MERCH_PER_WIN_PCT = 0.06  # ...and up to 3% more (or less) for winning (losing)
MERCH_MARKET = {"small": 0.8, "medium": 1.0, "large": 1.25}

# Profit goals (a share of the cap), by where the roster stands: a rebuilding team spends
# less, so its owner expects more.
PROFIT_TARGET = {"contender": 0.0, "middle": 0.04, "rebuilding": 0.08}


def ticket_price(market: str, price: str, salary_cap: int) -> int:
    """One seat at one game, in whole dollars."""
    return round(TICKET[market] * PRICE_FACTOR[price] * salary_cap / REFERENCE_CAP)


def attendance(market: str, mood: int, price: str) -> int:
    """Seats sold: from 55% of the stadium with the fans at their lowest to all of it at
    their happiest, more with cheap tickets and fewer with dear ones."""
    share = 0.55 + 0.45 * mood / 100 + PRICE_ATTENDANCE[price]
    return round(CAPACITY[market] * max(0.0, min(1.0, share)))


def merchandise(salary_cap: int, market: str, stars: int, win_pct: float) -> int:
    """A season's merchandise."""
    share = (MERCH_BASE + MERCH_PER_STAR * min(stars, 5)
             + MERCH_PER_WIN_PCT * (win_pct - 0.5))
    return round(salary_cap * max(0.0, share) * MERCH_MARKET[market])


def media(salary_cap: int) -> int:
    """A season's share of the media money (the same for every team)."""
    return round(salary_cap * MEDIA_SHARE)


def profit_target(salary_cap: int, situation: str) -> int:
    """A profit-minded owner's target for the season, rounded to $1M."""
    return round(salary_cap * PROFIT_TARGET[situation], -6)


@dataclass(frozen=True)
class Gate:
    """A home game's gate."""
    game_id: int
    week: int
    playoff: bool
    mood: int  # the fans' mood going into it
    attendance: int
    price: int
    revenue: int
