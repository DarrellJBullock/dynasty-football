import dataclasses
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.sim.calibration import default_league_teams
from app.sim.coaching import CoachCall, Situation, check_call, replay
from app.sim.gameplan import NEUTRAL, GamePlan, validate
from app.sim.look import (
    DISGUISE_MAX,
    DISGUISE_MIN,
    SAFETIES,
    defensive_look,
    disguise_rate,
    offensive_look,
)
from app.sim.playbook import OFFENSE_BY_KEY
from app.sim.teams import team_from_dict, team_to_dict

OFFENSE_AUDIBLES = GamePlan(offense_audibles=("slants", "inside_zone", "four_verts"))
DEFENSE_AUDIBLES = GamePlan(defense_audibles=("cover0", "cover2"))


@pytest.fixture(scope="module")
def teams():
    return default_league_teams()


def _fresh(teams, i: int, plan: GamePlan = NEUTRAL):
    team = team_from_dict(team_to_dict(teams[i]))
    team.plan = plan
    return team


def _coach(teams, plan: GamePlan, side: str, decisions: int, audible=lambda s: "keep",
           seed: int = 11):
    """Coach `decisions` calls of a game by taking the AI's suggestions, answering each
    stop at the line with `audible(situation)`."""
    calls: list[CoachCall] = []
    stops: list[Situation] = []
    outcome = None
    for _ in range(decisions):
        home = _fresh(teams, 0, plan if side == "home" else NEUTRAL)
        away = _fresh(teams, 1, plan if side == "away" else NEUTRAL)
        outcome = replay(home, away, seed, side, calls)
        s = outcome.situation
        if s is None:
            break
        if s.role == "audible":
            stops.append(s)
            calls[-1] = dataclasses.replace(calls[-1], audible=audible(s))
        else:
            calls.append(CoachCall(s.role, s.suggestion, s.suggested_package))
    return calls, stops, outcome


class TestTheLook:
    def test_smarter_defenses_disguise_more(self, teams):
        team = _fresh(teams, 0)
        rate = disguise_rate(team)
        assert DISGUISE_MIN <= rate <= DISGUISE_MAX
        for player in team.players.values():
            player.ratings["awareness"] = 99
        assert disguise_rate(team) == DISGUISE_MAX
        for player in team.players.values():
            player.ratings["awareness"] = 20
        assert disguise_rate(team) == DISGUISE_MIN

    def test_honest_most_of_the_time_and_disguised_sometimes(self, teams):
        team = _fresh(teams, 0)
        looks = [defensive_look("nickel", "cover2", False, team, random.Random(i))
                 for i in range(400)]
        assert all(look["package"] == "nickel" for look in looks)  # personnel can't hide
        honest = sum(look["safeties"] == SAFETIES["cover2"] for look in looks) / len(looks)
        assert 1 - DISGUISE_MAX - 0.05 <= honest <= 1 - DISGUISE_MIN + 0.05
        assert any(look["safeties"] == "single_high" for look in looks)
        assert any(look["blitz"] for look in looks)  # a faked blitz now and then

    def test_the_defense_sees_the_formation(self):
        assert offensive_look("pa_boot") == {"formation": OFFENSE_BY_KEY["pa_boot"].formation}
        assert offensive_look(None) == {"formation": None}


class TestAtTheLine:
    def test_no_audibles_in_the_plan_no_stop(self, teams):
        _, stops, _ = _coach(teams, NEUTRAL, "home", 30)
        assert stops == []

    def test_stops_at_the_line_after_each_call_on_offense(self, teams):
        _, stops, _ = _coach(teams, OFFENSE_AUDIBLES, "home", 30)
        assert stops
        stop = stops[0]
        assert (stop.role, stop.audible_for, stop.suggestion) == ("audible", "offense", "keep")
        assert stop.audibles == OFFENSE_AUDIBLES.offense_audibles
        assert stop.called and set(stop.look) == {"package", "safeties", "blitz"}

    def test_keeping_every_call_plays_the_game_unchanged(self, teams):
        """Seeing the look draws from its own stream: the game's other draws don't move."""
        with_audibles, stops, kept = _coach(teams, OFFENSE_AUDIBLES, "home", 40)
        without, _, plain = _coach(teams, NEUTRAL, "home", 40 - len(stops))
        assert [dataclasses.replace(c, audible=None) for c in with_audibles] == without
        assert [p.to_dict() for p in kept.plays] == [p.to_dict() for p in plain.plays]

    def test_an_audible_changes_the_call(self, teams):
        def switch(stop: Situation) -> str:
            return next(a for a in stop.audibles if a != stop.called)
        calls, stops, outcome = _coach(teams, OFFENSE_AUDIBLES, "home", 12, audible=switch)
        assert stops
        audibled = [p for p in outcome.plays if p.call and p.call.get("audible_from")]
        assert audibled
        first = audibled[0]
        assert first.call["play"] in OFFENSE_AUDIBLES.offense_audibles
        assert first.call["audible_from"] == stops[0].called
        # Replays are exact: the recorded audibles play the same game again (the helper
        # has already made the next call, so compare the plays both have).
        again = replay(_fresh(teams, 0, OFFENSE_AUDIBLES), _fresh(teams, 1), 11, "home", calls)
        played = [p.to_dict() for p in outcome.plays]
        assert [p.to_dict() for p in again.plays][:len(played)] == played

    def test_on_defense_the_look_is_the_formation(self, teams):
        def switch(stop: Situation) -> str:
            return "cover0" if stop.called != "cover0" else "cover2"
        _, stops, outcome = _coach(teams, DEFENSE_AUDIBLES, "away", 30, audible=switch)
        assert stops and stops[0].audible_for == "defense"
        assert set(stops[0].look) == {"formation"}
        audibled = [p for p in outcome.plays if p.defense and p.defense.get("audible_from")]
        assert audibled and audibled[0].defense["play"] in ("cover0", "cover2")


def test_what_can_be_said_at_the_line():
    stop = Situation(role="audible", quarter=1, clock=900, clock_running=False,
                     possession="home", down=1, distance=10, ball_on=25,
                     score={"home": 0, "away": 0}, timeouts={"home": 3, "away": 3},
                     suggestion="keep", suggested_package=None, audible_for="offense",
                     called="smash", look={}, audibles=("slants",))
    assert check_call(CoachCall("audible", "keep"), stop) is None
    assert check_call(CoachCall("audible", "slants"), stop) is None
    assert "Audible to one of: slants" in check_call(CoachCall("audible", "dig"), stop)
    assert "at the line" in check_call(CoachCall("offense", "smash"), stop)
    assert check_call(CoachCall("audible", "keep", timeout=True), stop)


def test_audibles_in_a_plan():
    assert validate(OFFENSE_AUDIBLES) == [] and validate(DEFENSE_AUDIBLES) == []
    lean = GamePlan(offense=frozenset({"inside_zone", "toss", "bubble", "slants", "dig",
                                       "four_verts"}),
                    offense_audibles=("smash", "slants", "slants", "dig", "toss"))
    assert validate(lean) == ["Up to 3 offensive audibles.",
                              "The offensive audibles repeat a play.",
                              "Offensive audibles must be in the plan: smash."]
    assert GamePlan.from_dict(OFFENSE_AUDIBLES.to_dict()) == OFFENSE_AUDIBLES
    assert "audibles" not in NEUTRAL.to_dict()


def test_coaching_with_audibles_through_the_api(client: TestClient, db: Session, franchise):
    url = f"/api/teams/{franchise.team_id}/game-plan"
    plan = client.get(url).json()
    saved = client.put(url, json={"offense": plan["offense"], "defense": plan["defense"],
                                  "tendencies": plan["tendencies"],
                                  "offense_audibles": ["slants", "inside_zone"],
                                  "defense_audibles": ["cover0"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["offense_audibles"] == ["slants", "inside_zone"]

    game_id = client.get("/api/franchise/next-game").json()["game"]["id"]
    state = client.post(f"/api/games/{game_id}/coach").json()
    db.commit()
    for _ in range(60):  # take the AI's calls until the first stop at the line
        situation = state["situation"]
        if situation["role"] == "audible":
            break
        state = client.post(f"/api/games/{game_id}/coach/auto", json={"scope": "play"}).json() \
            if situation["role"] in ("kickoff", "conversion") else client.post(
                f"/api/games/{game_id}/coach/call",
                json={"play": situation["suggestion"], "package": situation["suggested_package"]}
            ).json()
        db.commit()
    situation = state["situation"]
    assert situation["role"] == "audible"
    assert situation["suggestion_name"] == "Keep the call" and situation["called"]["name"]
    assert situation["look"]
    keys = [a["key"] for a in situation["audibles"]]
    assert keys in (["slants", "inside_zone"], ["cover0"])
    calls = state["calls"]

    bad = client.post(f"/api/games/{game_id}/coach/call", json={"play": "hail_mary"})
    assert bad.status_code == 422
    after = client.post(f"/api/games/{game_id}/coach/call", json={"play": keys[0]}).json()
    db.commit()
    assert after["calls"] == calls  # (the audible went onto the snap's call)
    assert after["new_plays"] >= 1
