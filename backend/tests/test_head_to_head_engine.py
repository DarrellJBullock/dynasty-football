"""Milestone 13, part 1: head-to-head in the engine
(docs/design/head-to-head-and-commissioner.md §3)."""

import pytest

from app.sim.calibration import default_league_teams
from app.sim.coaching import CoachCall, replay, replay_both
from app.sim.engine import simulate_game
from app.sim.gameplan import GamePlan
from app.sim.teams import team_from_dict, team_to_dict


@pytest.fixture(scope="module")
def teams():
    return default_league_teams()


def _fresh(teams, i: int):
    return team_from_dict(team_to_dict(teams[i]))


def _answer(calls: list[CoachCall], situation) -> None:
    """A coach's answer to a situation: the AI's suggestion (at the line: keep the call,
    stored on that snap's call, as the service does)."""
    if situation.role == "audible":
        last = calls[-1]
        calls[-1] = CoachCall(last.role, last.play, last.package, last.timeout, "keep")
    else:
        calls.append(CoachCall(situation.role, situation.suggestion, situation.suggested_package))


def _play_to_the_end(teams, seed=21, limit=800):
    """Both coaches take the AI's suggestion every time; returns their calls and the end."""
    calls = {"home": [], "away": []}
    for _ in range(limit):
        outcome = replay_both(_fresh(teams, 0), _fresh(teams, 1), seed, calls)
        if not outcome.needs:
            return calls, outcome
        for side, situation in outcome.needs.items():
            _answer(calls[side], situation)
    raise AssertionError("the game never ended")


class TestHeadToHead:
    def test_the_kickoff_is_one_call_then_each_snap_is_both(self, teams):
        first = replay_both(_fresh(teams, 0), _fresh(teams, 1), 3, {})
        assert len(first.needs) == 1
        (side, situation), = first.needs.items()
        assert situation.role == "kickoff"
        calls = {side: [CoachCall("kickoff", "normal")]}
        snap = replay_both(_fresh(teams, 0), _fresh(teams, 1), 3, calls)
        assert set(snap.needs) == {"home", "away"}
        assert {s.role for s in snap.needs.values()} == {"offense", "defense"}

    def test_a_snap_waits_for_both_calls(self, teams):
        calls = {}
        outcome = replay_both(_fresh(teams, 0), _fresh(teams, 1), 3, calls)
        (kicker, s), = outcome.needs.items()
        calls[kicker] = [CoachCall("kickoff", "normal")]
        outcome = replay_both(_fresh(teams, 0), _fresh(teams, 1), 3, calls)
        offense = next(side for side, s in outcome.needs.items() if s.role == "offense")
        before = len(outcome.plays)
        _answer(calls.setdefault(offense, []), outcome.needs[offense])
        waiting = replay_both(_fresh(teams, 0), _fresh(teams, 1), 3, calls)
        # The offense has called; the snap waits, blind, on the defense alone.
        assert set(waiting.needs) == {"home", "away"} - {offense}
        assert len(waiting.plays) == before

    def test_a_whole_game_replays_the_same_from_the_same_calls(self, teams):
        calls, end = _play_to_the_end(teams)
        assert end.result is not None
        again = replay_both(_fresh(teams, 0), _fresh(teams, 1), 21, calls)
        assert not again.needs
        assert (again.result.home_score, again.result.away_score) == (
            end.result.home_score, end.result.away_score)
        assert len(again.plays) == len(end.plays)
        # A game part way through stops at the same place every time.
        partial = {side: c[: len(c) // 2] for side, c in calls.items()}
        one = replay_both(_fresh(teams, 0), _fresh(teams, 1), 21, partial)
        two = replay_both(_fresh(teams, 0), _fresh(teams, 1), 21, partial)
        assert len(one.plays) == len(two.plays) and one.needs.keys() == two.needs.keys()

    def test_both_on_autopilot_is_the_ai_s_game(self, teams):
        auto = replay_both(_fresh(teams, 0), _fresh(teams, 1), 7, {},
                           autopilot={"home": True, "away": True})
        ai = simulate_game(_fresh(teams, 0), _fresh(teams, 1), 7)
        assert not auto.needs
        assert (auto.result.home_score, auto.result.away_score) == (ai.home_score, ai.away_score)
        assert len(auto.plays) == len(ai.plays)

    def test_one_side_on_autopilot_is_coach_mode(self, teams):
        calls = []
        for _ in range(40):
            single = replay(_fresh(teams, 0), _fresh(teams, 1), 11, "home", calls)
            both = replay_both(_fresh(teams, 0), _fresh(teams, 1), 11, {"home": calls},
                               autopilot={"away": True})
            assert len(both.plays) == len(single.plays)
            assert list(both.needs) == ["home"]
            assert both.needs["home"].role == single.situation.role
            _answer(calls, single.situation)

    def test_both_sides_may_audible_at_the_line(self, teams):
        plan = GamePlan(offense_audibles=("slants", "inside_zone"),
                        defense_audibles=("cover0", "cover2"))

        def team(i: int):
            t = _fresh(teams, i)
            t.plan = plan
            return t

        calls = {"home": [], "away": []}
        seen = []
        for _ in range(12):
            outcome = replay_both(team(0), team(1), 5, calls)
            for side, situation in outcome.needs.items():
                if situation.role == "audible":
                    seen.append((situation.audible_for, len(outcome.needs)))
                _answer(calls[side], situation)
        # At the line, one at a time: the offense, then the defense (each seeing the other).
        assert ("offense", 1) in seen and ("defense", 1) in seen
        assert seen.index(("offense", 1)) < seen.index(("defense", 1))
