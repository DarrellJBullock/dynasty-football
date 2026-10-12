"""Penalties (sim/penalties.py): which fouls a play allows, awareness-driven rates, and
each foul's enforcement in the engine (yards, spot, down, automatic first down)."""

import dataclasses
import random
import re
from pathlib import Path

import pytest

from app.sim.calibration import default_league_teams
from app.sim.engine import simulate_game
from app.sim.penalties import FOULS, NAMES, factor, live, pre_snap
from app.sim.resolve import Defense, Offense, Outcome
from app.sim.stats import box_score
from app.sim.teams import SimPlayer, SimTeam
from app.sim.tuning import DEFAULT_TUNING


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


def only(kind: str, rate: float = 0.3):
    """Tuning where `kind` is the only foul (pass interference off too)."""
    rates = dict.fromkeys(DEFAULT_TUNING.penalty_rates, 0.0) | {kind: rate}
    return dataclasses.replace(DEFAULT_TUNING, penalty_rates=rates,
                               pass_interference_rate=0.0)


def _p(pid: int, awareness: int = 72) -> SimPlayer:
    return SimPlayer(id=pid, name=f"P. {pid}", position="X", overall=70,
                     ratings={"awareness": awareness})


def _offense(awareness: int = 72) -> Offense:
    return Offense(qb=_p(1, awareness), rb=_p(2, awareness),
                   wrs=[_p(3, awareness), _p(4, awareness), _p(5, awareness)],
                   te=_p(6, awareness), tackles=[_p(7, awareness), _p(8, awareness)],
                   guards=[_p(9, awareness), _p(10, awareness)], center=_p(11, awareness))


def _defense() -> Defense:
    return Defense(ends=[_p(21), _p(22)], tackles=[_p(23), _p(24)], olbs=[_p(25), _p(26)],
                   mlb=_p(27), corners=[_p(28), _p(29)], fs=_p(30), ss=_p(31))


def test_every_foul_has_a_name_and_a_rate():
    assert set(FOULS) | {"pass_interference"} == set(NAMES)
    assert set(FOULS) == set(DEFAULT_TUNING.penalty_rates)


def test_the_frontend_names_fouls_the_same_way():
    source = (Path(__file__).parents[2] / "frontend/src/lib/penalties.ts").read_text()
    assert dict(re.findall(r'^  (\w+): "([^"]+)",$', source, re.M)) == NAMES


def test_awareness_sets_the_rate():
    t = DEFAULT_TUNING
    assert factor(_p(1, 72), t) == 1.0
    assert factor(_p(1, 55), t) > 1 > factor(_p(1, 85), t)
    assert factor(_p(1, 0), t) == 2.0 and factor(_p(1, 99), t) == 0.4

    def flags(awareness: int) -> int:
        rng, tuning = random.Random(3), only("false_start", 0.02)
        off, deff = _offense(awareness), _defense()
        return sum(bool(pre_snap(off, deff.front, deff.backers, rng, tuning))
                   for _ in range(20_000))

    assert flags(50) > 2.5 * flags(90)


@pytest.mark.parametrize("kind, outcome, ball_on, called", [
    # Offensive fouls only on plays that gained ground (else the defense declines).
    ("holding", Outcome("run", 6), 30, True),
    ("holding", Outcome("run", -2), 30, False),
    ("offensive_pass_interference", Outcome("pass", 12, result="complete"), 30, True),
    ("offensive_pass_interference", Outcome("run", 12), 30, False),
    # Defensive holding: only when the play gained less than the foul's 5 yards.
    ("defensive_holding", Outcome("pass", 0, result="incomplete"), 30, True),
    ("defensive_holding", Outcome("sack", -7), 30, True),
    ("defensive_holding", Outcome("pass", 9, result="complete"), 30, False),
    # Personal fouls: not on a scoring play.
    ("unnecessary_roughness", Outcome("run", 4), 30, True),
    ("unnecessary_roughness", Outcome("run", 12), 90, False),
    ("roughing_the_passer", Outcome("run", 4), 30, False),
    ("roughing_the_passer", Outcome("sack", -6), 30, False),
    ("roughing_the_passer", Outcome("pass", 0, result="incomplete"), 30, True),
    ("face_mask", Outcome("pass", 0, result="incomplete"), 30, False),
    # Grounding: only a throwaway.
    ("intentional_grounding", Outcome("pass", 0, result="throwaway"), 30, True),
    ("intentional_grounding", Outcome("pass", 0, result="incomplete"), 30, False),
    # Nothing on a turnover.
    ("unnecessary_roughness", Outcome("pass", 0, result="interception", turnover=True), 30,
     False),
])
def test_which_plays_allow_a_foul(kind, outcome, ball_on, called):
    foul = live(outcome, _offense(), _defense(), ball_on, random.Random(1), only(kind, 1.0))
    assert (foul is not None) == called
    if foul:
        assert foul["kind"] == kind and foul["team"] == FOULS[kind].team


def _flagged(teams, kind: str, games: int = 4, rate: float = 0.3):
    """(the flagged play, its foul, the next snap of the same drive) in games where `kind`
    is the only foul."""
    for seed in range(games):
        game = simulate_game(teams[0], teams[1], seed=seed, tuning=only(kind, rate))
        for play, nxt in zip(game.plays, game.plays[1:], strict=False):
            fouls = [e for e in play.events if e["t"] == "penalty"]
            if fouls and play.down is not None and nxt.down is not None \
                    and nxt.side == play.side:
                yield play, fouls[0], nxt


def test_false_start_backs_up_the_offense(teams):
    seen = 0
    for play, foul, nxt in _flagged(teams, "false_start"):
        seen += 1
        assert foul["team"] == play.offense and play.result == {"type": "penalty"}
        assert foul["yards"] == min(5, play.ball_on // 2)
        assert (nxt.ball_on, nxt.down, nxt.distance) == (
            play.ball_on - foul["yards"], play.down, play.distance + foul["yards"])
    assert seen > 10


def test_offside_moves_the_ball_forward(teams):
    seen = firsts = 0
    for play, foul, nxt in _flagged(teams, "offside"):
        seen += 1
        assert foul["team"] != play.offense
        assert nxt.ball_on == play.ball_on + foul["yards"]
        if foul["yards"] >= play.distance:
            firsts += 1
            assert play.result["first_down"] and nxt.down == 1
        else:
            assert (nxt.down, nxt.distance) == (play.down, play.distance - foul["yards"])
    assert seen > 10 and firsts


def test_holding_wipes_out_the_play(teams):
    seen = 0
    for play, foul, nxt in _flagged(teams, "holding"):
        seen += 1
        assert play.result == {"type": "penalty", "nullified": True}
        assert foul["yards"] == min(10, play.ball_on // 2)
        assert (nxt.ball_on, nxt.down) == (play.ball_on - foul["yards"], play.down)
    assert seen > 10


def test_defensive_holding_is_an_automatic_first_down(teams):
    seen = 0
    for play, foul, nxt in _flagged(teams, "defensive_holding"):
        seen += 1
        assert play.result == {"type": "penalty", "first_down": True}
        assert (nxt.ball_on, nxt.down) == (play.ball_on + foul["yards"], 1)
    assert seen > 5


def test_a_personal_foul_is_added_to_a_play_that_stands(teams):
    seen = 0
    for play, foul, nxt in _flagged(teams, "unnecessary_roughness"):
        seen += 1
        assert play.result["type"] in ("run", "pass", "sack", "scramble")
        assert play.result["first_down"] and "nullified" not in play.result
        assert nxt.ball_on == min(99, play.ball_on + play.result["yards"] + foul["yards"])
        assert nxt.down == 1
        assert "PENALTY" in play.text and "Unnecessary roughness, " in play.text
    assert seen > 10


def test_intentional_grounding_costs_the_down(teams):
    seen = 0
    for play, foul, nxt in _flagged(teams, "intentional_grounding", games=10, rate=1.0):
        seen += 1
        assert play.result["loss_of_down"] and "loss of down" in play.text
        assert (nxt.ball_on, nxt.down) == (play.ball_on - foul["yards"], play.down + 1)
    assert seen > 0  # (throwaways are rare: every one is flagged here)


def test_the_box_score_charges_the_team_that_fouled(teams):
    game = simulate_game(teams[0], teams[1], seed=2, tuning=only("holding"))
    box = box_score(game)
    for side in ("home", "away"):
        abbreviation = game.home.abbreviation if side == "home" else game.away.abbreviation
        flags = [e for p in game.plays for e in p.events
                 if e["t"] == "penalty" and e["team"] == abbreviation]
        assert flags  # (the offense holds: every flag is on the team with the ball)
        assert box.teams[side].penalties == len(flags)
        assert box.teams[side].penalty_yds == sum(e["yards"] for e in flags)
