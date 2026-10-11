"""Playoff rules: tiebreakers, seeding, and bracket pairing. Pure — no database.

Design: docs/design/simulation-engine.md §9.
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

SEED_OPTIONS = (7, 6, 4, 2)


@dataclass(frozen=True)
class Result:
    """A final regular-season game."""
    home: int
    away: int
    home_score: int
    away_score: int


@dataclass(frozen=True)
class TeamInfo:
    id: int
    division: int
    conference: int


@dataclass(frozen=True)
class Seed:
    team_id: int
    seed: int
    division_winner: bool


def seeds_per_conference(conference_teams: int) -> int:
    """7 for a 16-team conference; smaller conferences take the largest of 7/6/4/2 that is at
    most half their teams (minimum 2)."""
    for option in SEED_OPTIONS:
        if option <= conference_teams // 2:
            return option
    return min(2, conference_teams)


def _pct(wins: float, games: int) -> float:
    return wins / games if games else 0.0


class Ranker:
    """Orders teams by record, breaking ties in this sequence: win %, head-to-head among the
    tied group, division record, conference record, point differential, coin flip (seeded)."""

    def __init__(self, teams: Iterable[TeamInfo], results: Iterable[Result], salt: str):
        self.teams = {t.id: t for t in teams}
        self.results = list(results)
        self.salt = salt

    def _record(self, team_id: int, opponents: set[int] | None = None) -> tuple[float, int]:
        wins, games = 0.0, 0
        for r in self.results:
            if team_id not in (r.home, r.away):
                continue
            opponent = r.away if r.home == team_id else r.home
            if opponents is not None and opponent not in opponents:
                continue
            ours, theirs = ((r.home_score, r.away_score) if r.home == team_id
                            else (r.away_score, r.home_score))
            games += 1
            wins += 1 if ours > theirs else 0.5 if ours == theirs else 0
        return wins, games

    def win_pct(self, team_id: int) -> float:
        return _pct(*self._record(team_id))

    def _point_diff(self, team_id: int) -> int:
        diff = 0
        for r in self.results:
            if r.home == team_id:
                diff += r.home_score - r.away_score
            elif r.away == team_id:
                diff += r.away_score - r.home_score
        return diff

    def _coin(self, team_id: int) -> int:
        digest = hashlib.sha256(f"{self.salt}:{team_id}".encode()).digest()
        return int.from_bytes(digest[:4], "big")

    def rank(self, team_ids: Sequence[int]) -> list[int]:
        """Best first."""
        ids = list(team_ids)
        by_pct: dict[float, list[int]] = {}
        for team_id in ids:
            by_pct.setdefault(round(self.win_pct(team_id), 6), []).append(team_id)
        ordered: list[int] = []
        for pct in sorted(by_pct, reverse=True):
            group = by_pct[pct]
            ordered.extend(group if len(group) == 1 else self._break_tie(group))
        return ordered

    def _break_tie(self, group: list[int]) -> list[int]:
        members = set(group)

        def key(team_id: int) -> tuple:
            team = self.teams[team_id]
            division = ({t.id for t in self.teams.values() if t.division == team.division}
                        - {team_id})
            conference = ({t.id for t in self.teams.values() if t.conference == team.conference}
                          - {team_id})
            return (
                -_pct(*self._record(team_id, members - {team_id})),
                -_pct(*self._record(team_id, division)),
                -_pct(*self._record(team_id, conference)),
                -self._point_diff(team_id),
                self._coin(team_id),
            )

        return sorted(group, key=key)


def seed_conference(ranker: Ranker, conference_id: int) -> list[Seed]:
    """Division winners take the top seeds (by record), then the best remaining teams. If a
    conference has more divisions than seeds, only the best division winners qualify."""
    teams = [t for t in ranker.teams.values() if t.conference == conference_id]
    count = seeds_per_conference(len(teams))
    divisions = sorted({t.division for t in teams})
    winners = [ranker.rank([t.id for t in teams if t.division == d])[0] for d in divisions]
    winners = ranker.rank(winners)[:count]
    rest = ranker.rank([t.id for t in teams if t.id not in winners])
    order = winners + rest[:count - len(winners)]
    return [Seed(team_id=tid, seed=i + 1, division_winner=tid in winners)
            for i, tid in enumerate(order)]


def pair_round(alive_seeds: Sequence[int]) -> tuple[list[int], list[tuple[int, int]]]:
    """Given the seeds still alive in a conference, return (byes, games) for the next round.

    The highest remaining seed always hosts the lowest (reseeding). When the field isn't a
    power of two, the top seeds sit out so the next round is: 7 teams → 1 bye + 3 games,
    6 → 2 byes + 2 games.
    """
    seeds = sorted(alive_seeds)
    power = 1
    while power * 2 <= len(seeds):
        power *= 2
    games_needed = len(seeds) - power if power != len(seeds) else len(seeds) // 2
    byes = seeds[:len(seeds) - 2 * games_needed]
    playing = seeds[len(byes):]
    games = [(playing[i], playing[-1 - i]) for i in range(len(playing) // 2)]
    return byes, games


def conference_rounds(seed_count: int) -> int:
    """Rounds needed to crown a conference champion: 7 or 6 seeds → 3, 4 → 2, 2 → 1."""
    rounds, alive = 0, seed_count
    while alive > 1:
        byes, games = pair_round(list(range(1, alive + 1)))
        alive = len(byes) + len(games)
        rounds += 1
    return rounds


def round_names(seed_count: int, conferences: int) -> list[str]:
    """Names for every playoff round, first to last. With one conference, its final is the
    league Championship; with several, conference champions meet in the Championship."""
    rounds = conference_rounds(seed_count)
    early = {3: ["Wild Card", "Divisional"], 2: ["Semifinal"]}.get(rounds, [])
    if conferences > 1:
        return [*early, "Conference Championship", "Championship"]
    return [*early, "Championship"]
