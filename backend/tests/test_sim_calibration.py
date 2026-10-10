"""League-level realism and rating sensitivity (docs/design/simulation-engine.md §7).

Deterministic: fixed seeds mean these never flake; they fail only when an engine or
tuning change moves the league's football out of the target ranges.
"""

import dataclasses

import pytest

from app.sim.calibration import TARGETS, default_league_teams, measure
from app.sim.engine import simulate_game
from app.sim.teams import SimTeam


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


@pytest.fixture(scope="module")
def metrics(teams):
    return measure(teams, games=300, seed=1)


@pytest.mark.parametrize("metric", list(TARGETS))
def test_league_metric_in_target_range(metrics, metric):
    low, high = TARGETS[metric]
    assert low <= metrics.values[metric] <= high, metrics.report()


def test_home_field_advantage_is_modest(metrics):
    assert 52 <= metrics.values["home_win_pct"] <= 60


def _boosted(team: SimTeam, delta: int) -> SimTeam:
    def bump(p):
        return dataclasses.replace(
            p, overall=min(99, p.overall + delta),
            ratings={k: max(0, min(99, v + delta)) for k, v in p.ratings.items()})

    return SimTeam(team.id + 10_000, "FAV", "Favorite",
                   {slot: [bump(p) for p in players] for slot, players in team.depth.items()},
                   {pid: bump(p) for pid, p in team.players.items()})


def _favorite_win_pct(base: SimTeam, delta: int, games: int = 300) -> float:
    favorite = _boosted(base, delta)
    wins = 0
    for i in range(games):
        if i % 2:
            game = simulate_game(favorite, base, seed=i)
            wins += game.home_score > game.away_score
        else:
            game = simulate_game(base, favorite, seed=i)
            wins += game.away_score > game.home_score
    return 100 * wins / games


@pytest.mark.parametrize("delta, low, high", [(5, 65, 75), (10, 80, 90)])
def test_better_teams_win_more_but_not_always(teams, delta, low, high):
    base = sorted(teams, key=lambda t: t.pass_lean)[16]  # a mid-table, balanced team
    assert low <= _favorite_win_pct(base, delta) <= high
