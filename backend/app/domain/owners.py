"""Owners and fans (docs/design/owners-and-front-offices.md §3): what an owner wants, the goals
they set each season, how fans feel, and how the owner judges the season. Pure: no database.

Every number here is shown in the UI with how it was reached (pillar 3: readable depth).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain import money

PRIORITIES = {  # priority: what the owner wants, in words
    "win_now": "wants to win now",
    "build": "wants something that lasts",
    "profit": "wants the team to pay its way",
}
PATIENCE = (1, 5)  # 1: wants results this season; 5: gives a plan years
MARKETS = ("small", "medium", "large")
MARKET_SHARES = (0.25, 0.5, 0.25)  # a league's teams, by market (in order)

START_CONFIDENCE = 60  # a general manager's standing with a new owner
START_FAN_MOOD = {"small": 55, "medium": 50, "large": 45}  # big markets are harder to please
HOT_SEAT = 30  # below this, the owner is losing patience

# Fan mood: drifts a quarter of the way back to 50 each season, and moves with the season.
FAN_DRIFT = 0.25
FAN_WIN_SWING = 40  # a 1.000 season +20, a .000 season −20
FAN_PLAYOFFS = 5
FAN_PLAYOFF_WIN = 3
FAN_TITLE = 10
FAN_STAR = 1  # each star (85+ overall), up to FAN_STARS
FAN_STARS = 5
STAR_OVERALL = 85

# Owner confidence: each goal met or missed, and the fans.
PRIMARY_WEIGHT = 10
SECONDARY_WEIGHT = 6
FAN_CONFIDENCE_DIVISOR = 5  # (fan mood − 50) / 5: −10..+10

# What a team's roster says about its season (by team rating, among the league's).
SITUATIONS = ("contender", "middle", "rebuilding")
EXPECTED_WIN_PCT = {"contender": 0.65, "middle": 0.5, "rebuilding": 0.35}
YOUNG_AGE = 25

GOAL_LABELS = {
    "wins": "Win {target} games",
    "winning": "Finish .500 or better",
    "playoffs": "Make the playoffs",
    "playoff_win": "Win a playoff game",
    "title": "Win the championship",
    "division": "Win the division",
    "young": "Start {target} players aged {age} or younger",
    "fans": "Keep fan mood at {target} or better",
    "profit": "Make a profit of {millions}",
}


@dataclass(frozen=True)
class NewOwner:
    priority: str
    patience: int


def make(rng: random.Random) -> NewOwner:
    return NewOwner(priority=rng.choice(list(PRIORITIES)), patience=rng.randint(*PATIENCE))


def markets(rng: random.Random, count: int) -> list[str]:
    """A league's markets: a quarter small, half medium, a quarter large, shuffled."""
    small = round(count * MARKET_SHARES[0])
    large = round(count * MARKET_SHARES[2])
    spread = ["small"] * small + ["large"] * large + ["medium"] * (count - small - large)
    rng.shuffle(spread)
    return spread


def situation(rank: int, teams: int) -> str:
    """By team rating: the top third contend, the bottom third rebuild (rank 1: best)."""
    third = round(teams / 3)
    if rank <= third:
        return "contender"
    if rank > teams - third:
        return "rebuilding"
    return "middle"


@dataclass(frozen=True)
class Goal:
    kind: str
    target: int
    weight: int

    @property
    def label(self) -> str:
        if self.kind == "profit" and self.target <= 0:
            return "Turn a profit"
        return GOAL_LABELS[self.kind].format(target=self.target, age=YOUNG_AGE,
                                             millions=f"${self.target / 1_000_000:.0f}M")


def goals(priority: str, place: str, weeks: int, salary_cap: int) -> list[Goal]:
    """The season's goals: one from what the owner wants, one or two from where the roster
    stands."""
    wins = max(1, round(EXPECTED_WIN_PCT[place] * weeks))
    primary = {
        ("win_now", "contender"): Goal("title", 1, PRIMARY_WEIGHT),
        ("win_now", "middle"): Goal("playoffs", 1, PRIMARY_WEIGHT),
        ("win_now", "rebuilding"): Goal("winning", 1, PRIMARY_WEIGHT),
        ("build", "contender"): Goal("playoff_win", 1, PRIMARY_WEIGHT),
        ("build", "middle"): Goal("young", 6, PRIMARY_WEIGHT),
        ("build", "rebuilding"): Goal("young", 8, PRIMARY_WEIGHT),
    }.get((priority, place)) or Goal("profit", money.profit_target(salary_cap, place),
                                     PRIMARY_WEIGHT)
    chosen = [primary, Goal("wins", wins, SECONDARY_WEIGHT)]
    if place == "contender" and primary.kind != "playoffs":
        chosen.append(Goal("playoffs", 1, SECONDARY_WEIGHT))
    return chosen


@dataclass(frozen=True)
class Season:
    """What a team's season came to (or has come to so far)."""
    wins: int
    losses: int
    ties: int
    weeks: int  # the regular season's length
    playoffs: bool = False
    playoff_wins: int = 0
    title: bool = False
    division: bool = False
    young_starters: int = 0
    stars: int = 0
    ticket_price: str = "normal"
    profit: int = 0  # so far (the season's, once it's over)
    projected_profit: int = 0  # the season's, at this pace

    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.played if self.played else 0.5


def fan_change(season: Season) -> list[tuple[str, int]]:
    """How the season moved the fans, part by part (so far: scaled by games played)."""
    share = min(1.0, season.played / season.weeks) if season.weeks else 0.0
    parts = [("Record", round((season.win_pct - 0.5) * FAN_WIN_SWING * share))]
    if season.playoffs:
        parts.append(("Made the playoffs", FAN_PLAYOFFS))
    if season.playoff_wins:
        parts.append(("Playoff wins", FAN_PLAYOFF_WIN * season.playoff_wins))
    if season.title:
        parts.append(("Champions", FAN_TITLE))
    if season.ticket_price != "normal" and share:
        label = "Cheap tickets" if season.ticket_price == "low" else "Dear tickets"
        parts.append((label, round(money.PRICE_FAN_MOOD[season.ticket_price] * share)))
    stars = min(season.stars, FAN_STARS)
    if stars:
        parts.append((f"{stars} star player{'s' if stars != 1 else ''}", FAN_STAR * stars))
    return parts


def fan_mood(base: int, season: Season, drift: bool = False) -> int:
    """Fan mood: last season's (drifting back toward 50 at the season's end) and this
    season's so far."""
    mood = base + ((50 - base) * FAN_DRIFT if drift else 0)
    return clamp(round(mood + sum(v for _, v in fan_change(season))))


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def met(goal: Goal, season: Season, mood: int, final: bool) -> bool | None:
    """Whether the goal is met (True), missed (False), or not decided yet (None)."""
    if goal.kind == "wins":
        if season.wins >= goal.target:
            return True
        return False if season.wins + (season.weeks - season.played) < goal.target else None
    if goal.kind == "winning":
        return season.win_pct >= 0.5 if final else None
    if goal.kind == "playoffs":
        return True if season.playoffs else (False if final else None)
    if goal.kind == "playoff_win":
        return True if season.playoff_wins else (False if final else None)
    if goal.kind == "title":
        return True if season.title else (False if final else None)
    if goal.kind == "division":
        return True if season.division else (False if final else None)
    if goal.kind == "young":
        return season.young_starters >= goal.target if final else None
    if goal.kind == "fans":
        return mood >= goal.target if final else None
    if goal.kind == "profit":
        return season.profit >= goal.target if final else None
    raise ValueError(goal.kind)


def on_track(goal: Goal, season: Season, mood: int) -> bool:
    """For a goal not yet decided: is the team on course for it?"""
    pace = season.win_pct
    if goal.kind == "wins":
        return season.wins + pace * (season.weeks - season.played) >= goal.target
    if goal.kind in ("winning", "playoffs", "division"):
        return pace >= 0.5 + (0.1 if goal.kind != "winning" else 0)
    if goal.kind in ("playoff_win", "title"):
        return pace >= 0.65
    if goal.kind == "young":
        return season.young_starters >= goal.target
    if goal.kind == "fans":
        return mood >= goal.target
    if goal.kind == "profit":
        return season.projected_profit >= goal.target
    raise ValueError(goal.kind)


def confidence_change(goals_met: Sequence[tuple[Goal, bool]], patience: int,
                      mood: int) -> list[tuple[str, int]]:
    """How the season moved the owner, part by part: each goal (a patient owner forgives a
    miss more), and the fans."""
    parts = []
    for goal, done in goals_met:
        if done:
            parts.append((goal.label, goal.weight))
        else:
            parts.append((goal.label, -round(goal.weight * (1.5 - 0.2 * patience))))
    parts.append(("Fan mood", round((mood - 50) / FAN_CONFIDENCE_DIVISOR)))
    return parts


def verdict(change: int, confidence: int) -> str:
    """The owner's word on the season."""
    if confidence < HOT_SEAT:
        return "is losing patience"
    if change >= 15:
        return "is delighted"
    if change >= 5:
        return "is pleased"
    if change > -5:
        return "is satisfied"
    if change > -15:
        return "is disappointed"
    return "is angry"
