"""The Hall of Fame's legacy score (docs/design/staff-and-legacy.md §4). Pure.

A retired player's case is his career production, ranked against everyone who has played
his position in the league (so a lineman's long career counts as much as a passer's
yards), plus his awards, championships and seasons as a regular. The best cases over the
bar get in, a few a year.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.awards import AWARDS, defense_points, offense_points, summary
from app.domain.positions import DEFENSE, Position

ELIGIBLE_AFTER = 3  # seasons after retiring
CLASS_MAX = 4  # inductees a year
BAR = 60.0  # the score a case needs
BALLOT_SHOWN = 6  # cases kept from each year's ballot below the bar (the near misses)

PRODUCTION_POINTS = 50.0  # for the best career at the position (scaled by percentile)
AWARD_POINTS = {"mvp": 12.0, "opoy": 8.0, "dpoy": 8.0, "oroy": 3.0, "droy": 3.0}
TITLE_POINTS = 4.0
SEASON_POINTS = 1.5  # per season as a regular...
SEASONS_COUNTED = 12  # ...up to this many
REGULAR_SHARE = 0.5  # of a season's games, to count as a regular

LINE = {Position.OT, Position.OG, Position.C}


@dataclass
class Career:
    """A player's career in the league: regular-season totals, and what came with them."""
    player_id: int
    position: str
    games: int = 0
    stats: dict[str, int] = field(default_factory=dict)
    regular_seasons: int = 0  # seasons he played at least REGULAR_SHARE of the games
    awards: dict[str, int] = field(default_factory=dict)  # award -> times won
    titles: int = 0


def production(position: str, stats: Mapping[str, int]) -> float:
    """What a career produced, in the terms of its position. Linemen are measured by the
    snaps they played; kickers by points and punters by yards."""
    pos = Position(position)
    if pos in LINE:
        return stats.get("snaps", 0) / 20
    if pos == Position.K:
        return stats.get("fg_made", 0) * 3 + stats.get("xp_made", 0)
    if pos == Position.P:
        return stats.get("punt_yds", 0) / 40
    if pos in DEFENSE:
        return defense_points(stats)
    return offense_points(stats)


def percentiles(careers: Sequence[Career]) -> dict[int, float]:
    """Each career's standing among everyone at its position (0 to 1; the best is 1)."""
    by_position: dict[str, list[tuple[float, int]]] = {}
    for c in careers:
        by_position.setdefault(c.position, []).append((production(c.position, c.stats),
                                                       c.player_id))
    ranks = {}
    for group in by_position.values():
        group.sort()
        n = len(group)
        for i, (_value, player_id) in enumerate(group):
            ranks[player_id] = (i + 1) / n
    return ranks


def score(career: Career, percentile: float) -> float:
    return (PRODUCTION_POINTS * percentile
            + sum(AWARD_POINTS[a] * n for a, n in career.awards.items())
            + TITLE_POINTS * career.titles
            + SEASON_POINTS * min(career.regular_seasons, SEASONS_COUNTED))


def case(career: Career) -> str:
    """The case for him, in a line: "3× MVP · 2 titles · 41,250 pass yds · 12 seasons"."""
    parts = [f"{n}× {_short(a)}" if n > 1 else _short(a)
             for a, n in sorted(career.awards.items(), key=lambda kv: list(AWARDS).index(kv[0]))]
    if career.titles:
        parts.append(f"{career.titles} title{'s' if career.titles > 1 else ''}")
    pos = Position(career.position)
    if pos in LINE:
        parts.append(f"{career.stats.get('snaps', 0):,} snaps")
    elif pos == Position.K:
        parts.append(f"{career.stats.get('fg_made', 0):,} field goals")
    elif pos == Position.P:
        parts.append(f"{career.stats.get('punt_yds', 0):,} punt yds")
    else:
        parts.append(summary(career.position, career.stats))
    parts.append(f"{career.regular_seasons} season{'s' if career.regular_seasons != 1 else ''}")
    return " · ".join(parts)[:200]


def _short(award: str) -> str:
    return {"mvp": "MVP", "opoy": "OPOY", "dpoy": "DPOY", "oroy": "OROY",
            "droy": "DROY"}[award]


def ballot(eligible: Sequence[tuple[Career, float]]) -> tuple[list[int], list[int]]:
    """Of the eligible (career, score), who gets in this year (the best over the bar, up to
    CLASS_MAX) and the near misses kept on the ballot. Ties go to the lower player id."""
    ranked = sorted(eligible, key=lambda cs: (-cs[1], cs[0].player_id))
    inducted = [c.player_id for c, s in ranked if s >= BAR][:CLASS_MAX]
    misses = [c.player_id for c, _s in ranked if c.player_id not in inducted][:BALLOT_SHOWN]
    return inducted, misses
