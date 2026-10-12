"""Special teams: onside kicks and squibs, the AI's kicking decisions, and the coach's."""

import random
from statistics import mean

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoachedGame
from app.sim.calibration import default_league_teams
from app.sim.coaching import CoachCall, check_call, replay
from app.sim.engine import simulate_game
from app.sim.playcalls import AICoach
from app.sim.resolve import resolve_onside, resolve_squib
from app.sim.state import GameState
from app.sim.teams import team_from_dict, team_to_dict
from app.sim.text import describe
from app.sim.tuning import DEFAULT_TUNING
from tests.test_coach import _situation


@pytest.fixture(scope="module")
def teams():
    return default_league_teams()


def _fresh(teams, i: int):
    return team_from_dict(team_to_dict(teams[i]))


class TestKicks:
    def test_onside_kicks_are_recovered_about_one_time_in_eight(self, teams):
        rng = random.Random(1)
        kicker = teams[0].one("K")
        trials = [resolve_onside(kicker, teams[0], teams[1], rng, DEFAULT_TUNING)
                  for _ in range(3000)]
        rate = mean(recovered for recovered, _, _ in trials)
        assert 0.08 < rate < 0.18
        for recovered, spot, event in trials[:50]:
            assert 45 <= spot <= 48  # 10-13 yards from the 35
            assert event["kind"] == "onside" and event["recovered"] == recovered
            assert event["return"] == 100 - spot
            side = teams[0] if recovered else teams[1]
            assert event["recovered_by"] in side.players or event["recovered_by"] < 0

    def test_better_hands_recover_more(self, teams):
        kicker = teams[0].one("K")
        weak = _fresh(teams, 1)
        for p in weak.players.values():
            p.ratings["catching"] = 40  # (ratings are plain dicts in a snapshot)

        def rate(kicking, receiving):
            rng = random.Random(4)
            return mean(resolve_onside(kicker, kicking, receiving, rng, DEFAULT_TUNING)[0]
                        for _ in range(3000))

        assert rate(teams[0], weak) > rate(weak, teams[0]) + 0.05

    def test_squibs_land_short_and_cant_be_returned_far(self, teams):
        rng = random.Random(2)
        spots = [resolve_squib(teams[0].one("K"), rng, DEFAULT_TUNING)[0] for _ in range(500)]
        assert all(15 <= s <= 45 for s in spots)
        assert 29 < mean(spots) < 35


class TestAIDecisions:
    def test_kickoffs(self):
        s = GameState(quarter=4, clock=200, score={"home": 10, "away": 17})
        assert AICoach.kickoff_call(s, "home") == "onside"  # down 7, 3:20 left
        assert AICoach.kickoff_call(s, "away") == "normal"  # ahead
        assert AICoach.kickoff_call(GameState(quarter=4, clock=600, score={"home": 10, "away": 17}),
                                    "home") == "normal"  # time to kick deep
        assert AICoach.kickoff_call(GameState(quarter=4, clock=200, score={"home": 0, "away": 21}),
                                    "home") == "normal"  # three scores down: no point
        assert AICoach.kickoff_call(GameState(quarter=2, clock=12), "home") == "squib"
        assert AICoach.kickoff_call(GameState(quarter=1, clock=12), "home") == "normal"

    def test_conversions(self):
        assert AICoach().conversion_call(GameState(quarter=4, clock=250,
                                                 score={"home": 15, "away": 17}), "home") == "two"
        assert AICoach().conversion_call(GameState(quarter=4, clock=250,
                                                 score={"home": 16, "away": 17}), "home") == "kick"
        assert AICoach().conversion_call(GameState(quarter=3, clock=250,
                                                 score={"home": 15, "away": 17}), "home") == "kick"


class _Onside(AICoach):
    """Onside kicks every time."""

    @staticmethod
    def kickoff_call(s, side):
        return "onside"


def test_onside_kicks_in_a_game(teams):
    coach = _Onside()
    game = simulate_game(_fresh(teams, 0), _fresh(teams, 1), seed=3,
                         coaches={"home": coach, "away": coach})
    kicks = [(i, p) for i, p in enumerate(game.plays) if p.result["type"] == "kickoff"]
    assert kicks
    seen = set()
    for i, kick in kicks:
        event = kick.events[0]
        assert event["kind"] == "onside"
        nxt = game.plays[i + 1] if i + 1 < len(game.plays) else None
        if nxt is None or nxt.ball_on is None:
            continue
        recovered = event["recovered"]
        seen.add(recovered)
        kicking = kick.side
        assert (nxt.side == kicking) == recovered
        spot = 100 - event["return"]  # the kicking team's yard line
        assert nxt.ball_on == (spot if recovered else event["return"])
        assert ("RECOVERED by" in kick.text) == recovered
    assert seen  # (and over many seeds both outcomes happen; see the rate test)


def test_text():
    from app.sim.engine import PlayRecord

    def play(event):
        return PlayRecord(n=1, quarter=1, clock="15:00", offense="HFD", side="home", down=None,
                          distance=None, ball_on=None, call=None, defense=None,
                          result={"type": "kickoff"}, events=[event], elapsed=0,
                          score={"home": 0, "away": 0})

    names = {1: "S. Merritt", 2: "G. Draper"}
    onside = {"t": "kickoff", "kicker": 1, "touchback": False, "return": 54, "kind": "onside",
              "recovered": True, "recovered_by": 2}
    assert describe(play(onside), names, {}) == \
        "S. Merritt onside kick, RECOVERED by G. Draper for the kicking team."
    assert "of the receiving team" in describe(play({**onside, "recovered": False}), names, {})
    squib = {"t": "kickoff", "kicker": 1, "touchback": False, "return": 31, "kind": "squib"}
    assert describe(play(squib), names, {}) == "S. Merritt squib kicks, returned to the 31."


class TestCoachDecisions:
    def test_the_coach_makes_the_kicking_decisions(self, teams):
        calls: list[CoachCall] = []
        roles = set()
        two_tried = False
        for _ in range(500):
            outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 8, "home", calls)
            s = outcome.situation
            if s is None:
                break
            roles.add(s.role)
            choice = s.suggestion
            if s.role == "conversion" and not two_tried:
                choice, two_tried = "two", True
            calls.append(CoachCall(s.role, choice, s.suggested_package))
        assert outcome.situation is None
        assert {"kickoff", "conversion"} <= roles
        twos = [e for p in outcome.plays for e in p.events if e["t"] == "two_point"]
        assert twos and all(p.side == "home" for p in outcome.plays
                            if any(e["t"] == "two_point" for e in p.events))

    def test_onside_by_choice(self, teams):
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 8, "home", [])
        calls: list[CoachCall] = []
        while outcome.situation and outcome.situation.role != "kickoff":
            s = outcome.situation
            calls.append(CoachCall(s.role, s.suggestion, s.suggested_package))
            outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 8, "home", calls)
        calls.append(CoachCall("kickoff", "onside"))
        after = replay(_fresh(teams, 0), _fresh(teams, 1), 8, "home", calls)
        kick = after.plays[len(outcome.plays)]
        assert kick.events[0]["kind"] == "onside" and kick.side == "home"

    def test_check_kicking_calls(self):
        kickoff = _situation(role="kickoff", suggestion="normal")
        assert check_call(CoachCall("kickoff", "squib"), kickoff) is None
        assert check_call(CoachCall("kickoff", "smash"), kickoff) == \
            "Choose one of: normal, squib, onside."
        assert check_call(CoachCall("offense", "smash"), kickoff) == "This is a kickoff decision."
        assert check_call(CoachCall("kickoff", "onside", None, True), kickoff)
        conversion = _situation(role="conversion", suggestion="kick")
        assert check_call(CoachCall("conversion", "two"), conversion) is None
        assert check_call(CoachCall("conversion", "punt"), conversion)


def test_a_game_from_an_older_engine_can_be_abandoned(client: TestClient, db: Session, league):
    season = league.seasons[0]
    game_id = client.get("/api/franchise/next-game").json()["game"]["id"]
    client.post(f"/api/games/{game_id}/coach")
    coached = db.scalar(select(CoachedGame).where(CoachedGame.game_id == game_id))
    # Calls recorded by an engine that asked for different decisions.
    coached.calls = [CoachCall("conversion", "two").to_dict()]
    db.commit()
    response = client.get(f"/api/games/{game_id}/coach")
    assert response.status_code == 409 and "older version" in response.json()["detail"]

    assert client.delete(f"/api/games/{game_id}/coach").status_code == 204
    db.commit()
    assert client.get(f"/api/games/{game_id}/coach").status_code == 404
    assert client.get("/api/franchise/next-game").json()["coaching"] is False
    result = client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
    assert result.status_code == 200
    assert client.delete(f"/api/games/{game_id}/coach").status_code == 404


def test_playback_knows_who_recovered_an_onside_kick(client: TestClient, db: Session, league):
    from app.models import Game
    from app.services.playback import game_playback

    game = db.scalars(select(Game).where(Game.season_id == league.seasons[0].id)).first()
    kicking, receiving = game.home_team, game.away_team
    kicker = next(p for p in kicking.players if p.position == "K")
    ours = next(p for p in kicking.players if p.position == "WR")
    theirs = next(p for p in receiving.players if p.position == "WR")

    def kick(recovered: bool, by: int) -> dict:
        return {"n": 1, "quarter": 4, "clock": "3:00", "offense": kicking.abbreviation,
                "side": "home", "down": None, "distance": None, "ball_on": None, "call": None,
                "defense": None, "result": {"type": "kickoff"}, "elapsed": 3,
                "score": {"home": 10, "away": 17}, "text": "Onside kick.", "personnel": None,
                "events": [{"t": "kickoff", "kicker": kicker.id, "touchback": False,
                            "return": 54, "kind": "onside", "recovered": recovered,
                            "recovered_by": by}]}

    game.play_log = [kick(True, ours.id), {**kick(False, theirs.id), "n": 2}]
    game.status = "final"
    db.flush()
    playback = game_playback(db, game)
    teams = {p.id: p.team_id for p in playback.players}
    assert teams[ours.id] == kicking.id and teams[theirs.id] == receiving.id
    event = playback.plays[0].events[0]
    assert event.kind == "onside" and event.recovered and event.recovered_by == ours.id
