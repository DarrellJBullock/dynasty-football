"""Season awards from regular-season stat lines. Pure.

Offense scores yards and touchdowns (fantasy-style); defense scores tackles, sacks,
takeaways, and passes defended. The MVP is the best offensive season (quarterbacks'
weighted up) plus a bonus for the team's wins, so it leans to quarterbacks on winners;
Player of the Year awards go to the best season on each side, and Rookie of the Year to
the best by a first-year player.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.positions import DEFENSE, OFFENSE, Position

AWARDS = {
    "mvp": "Most Valuable Player",
    "opoy": "Offensive Player of the Year",
    "dpoy": "Defensive Player of the Year",
    "oroy": "Offensive Rookie of the Year",
    "droy": "Defensive Rookie of the Year",
}
MIN_GAME_SHARE = 0.5  # of the regular season, to qualify
MVP_WIN_BONUS = 4.0  # points per team win
MVP_QB_WEIGHT = 1.2  # quarterbacks touch every snap: their seasons count for more


def offense_points(s: Mapping[str, int]) -> float:
    return (s.get("pass_yds", 0) / 25 + s.get("pass_td", 0) * 4 - s.get("pass_int", 0) * 2
            + s.get("rush_yds", 0) / 10 + s.get("rush_td", 0) * 6
            + s.get("rec_yds", 0) / 10 + s.get("rec_td", 0) * 6 + s.get("receptions", 0) * 0.5
            - s.get("fumbles_lost", 0) * 2)


def defense_points(s: Mapping[str, int]) -> float:
    return (s.get("tackles", 0) + s.get("sacks", 0) * 4 + s.get("interceptions", 0) * 5
            + s.get("passes_defended", 0) * 1.5 + s.get("forced_fumbles", 0) * 3
            + s.get("int_return_yds", 0) / 10)


@dataclass(frozen=True)
class Candidate:
    player_id: int
    position: str
    games: int
    stats: Mapping[str, int]
    team_wins: int
    rookie: bool


def choose(candidates: Sequence[Candidate], weeks: int) -> dict[str, Candidate]:
    """Winner of each award (an award with no qualifying candidate is skipped)."""
    eligible = [c for c in candidates if c.games >= weeks * MIN_GAME_SHARE]
    offense = [c for c in eligible if Position(c.position) in OFFENSE]
    defense = [c for c in eligible if Position(c.position) in DEFENSE]

    def best(pool: Sequence[Candidate], score) -> Candidate | None:
        return max(pool, key=lambda c: (score(c), -c.player_id), default=None)

    def mvp_score(c: Candidate) -> float:
        weight = MVP_QB_WEIGHT if c.position == Position.QB.value else 1.0
        return offense_points(c.stats) * weight + c.team_wins * MVP_WIN_BONUS

    winners = {
        "mvp": best(offense, mvp_score),
        "opoy": best(offense, lambda c: offense_points(c.stats)),
        "dpoy": best(defense, lambda c: defense_points(c.stats)),
        "oroy": best([c for c in offense if c.rookie], lambda c: offense_points(c.stats)),
        "droy": best([c for c in defense if c.rookie], lambda c: defense_points(c.stats)),
    }
    return {award: c for award, c in winners.items() if c is not None}


def summary(position: str, s: Mapping[str, int]) -> str:
    """The headline numbers of a season, by position."""
    def n(key: str) -> str:
        return f"{s.get(key, 0):,}"

    pos = Position(position)
    if pos == Position.QB:
        return f"{n('pass_yds')} pass yds · {n('pass_td')} TD · {n('pass_int')} INT"
    if pos in (Position.RB, Position.FB):
        return f"{n('rush_yds')} rush yds · {s.get('rush_td', 0) + s.get('rec_td', 0)} TD"
    if pos in OFFENSE:
        return f"{n('receptions')} rec · {n('rec_yds')} yds · {n('rec_td')} TD"
    return (f"{n('tackles')} tackles · {n('sacks')} sacks · {n('interceptions')} INT")
