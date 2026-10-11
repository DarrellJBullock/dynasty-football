"""Coach Mode: replaying a coached game from the user's calls, and the coach API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoachedGame, Game, League, Season
from app.sim.calibration import default_league_teams
from app.sim.coaching import CoachCall, Situation, check_call, replay
from app.sim.engine import simulate_game
from app.sim.teams import team_from_dict, team_to_dict


@pytest.fixture(scope="module")
def teams():
    return default_league_teams()


def _fresh(teams, i: int):
    """A copy of a league team (the engine mutates in-game state)."""
    return team_from_dict(team_to_dict(teams[i]))


def _coach_to_the_end(teams, side="home", seed=21, limit=400):
    """Coach a whole game by always taking the AI's suggestion."""
    calls: list[CoachCall] = []
    for _ in range(limit):
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), seed, side, calls)
        s = outcome.situation
        if s is None:
            return calls, outcome
        calls.append(CoachCall(s.role, s.suggestion, s.suggested_package))
    raise AssertionError("the game never ended")


class TestReplay:
    def test_stops_at_the_first_call(self, teams):
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 3, "home", [])
        s = outcome.situation
        assert outcome.result is None and s is not None
        assert s.quarter == 1 and s.down == 1 and s.suggestion
        assert outcome.plays and outcome.plays[0].result["type"] == "kickoff"
        assert (s.role == "offense") == (s.possession == "home")

    def test_a_coached_game_plays_to_the_end_and_replays_exactly(self, teams):
        calls, outcome = _coach_to_the_end(teams)
        assert outcome.result is not None
        assert outcome.result.plays == outcome.plays
        again = replay(_fresh(teams, 0), _fresh(teams, 1), 21, "home", calls)
        assert [p.to_dict() for p in again.plays] == [p.to_dict() for p in outcome.plays]

    def test_partial_replays_are_prefixes_of_the_game(self, teams):
        calls, full = _coach_to_the_end(teams)
        whole = [p.to_dict() for p in full.plays]
        for k in (0, 5, 20, len(calls) // 2, len(calls) - 1):
            partial = replay(_fresh(teams, 0), _fresh(teams, 1), 21, "home", calls[:k])
            assert partial.situation is not None
            plays = [p.to_dict() for p in partial.plays]
            assert plays == whole[:len(plays)]

    def test_the_users_calls_are_the_calls_made(self, teams):
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 3, "home", [])
        calls: list[CoachCall] = []
        for _ in range(12):
            s = outcome.situation
            assert s is not None
            play = "four_verts" if s.role == "offense" else "cover0"
            calls.append(CoachCall(s.role, play, "nickel" if s.role == "defense" else None))
            outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 3, "home", calls)
        snaps = [p for p in outcome.plays if p.call and p.call["type"] in ("run", "pass")]
        ours = [p for p in snaps if p.side == "home"]
        theirs = [p for p in snaps if p.side == "away" and p.defense]
        assert ours and all(p.call["play"] == "four_verts" for p in ours)
        assert theirs and all(p.defense["play"] == "cover0" and p.defense["package"] == "nickel"
                              for p in theirs)

    def test_a_timeout_saves_the_runoff(self, teams):
        calls: list[CoachCall] = []
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 21, "home", calls)
        while not (outcome.situation.clock_running and outcome.situation.role == "offense"):
            s = outcome.situation
            calls.append(CoachCall(s.role, s.suggestion, s.suggested_package))
            outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 21, "home", calls)
        s = outcome.situation
        timed = replay(_fresh(teams, 0), _fresh(teams, 1), 21, "home",
                       [*calls, CoachCall(s.role, "slants", None, True)])
        snap = timed.plays[len(outcome.plays)]
        assert snap.clock == f"{s.clock // 60}:{s.clock % 60:02d}"  # no time ran off
        assert timed.situation.timeouts["home"] == s.timeouts["home"] - 1

    def test_autopilot_finishes_the_game(self, teams):
        outcome = replay(_fresh(teams, 0), _fresh(teams, 1), 3, "away", [], autopilot=True)
        assert outcome.situation is None and outcome.result is not None

    def test_snapshots_play_the_same_game(self, teams):
        a = simulate_game(_fresh(teams, 4), _fresh(teams, 5), seed=9)
        b = simulate_game(teams[4], teams[5], seed=9)
        assert [p.to_dict() for p in a.plays] == [p.to_dict() for p in b.plays]


def _situation(**overrides) -> Situation:
    base = dict(role="offense", quarter=2, clock=300, clock_running=True, possession="home",
                down=1, distance=10, ball_on=40, score={"home": 0, "away": 0},
                timeouts={"home": 2, "away": 0}, suggestion="slants", suggested_package=None)
    return Situation(**{**base, **overrides})


def test_check_call():
    s = _situation()
    assert check_call(CoachCall("offense", "smash"), s) is None
    assert check_call(CoachCall("offense", "smash", None, True), s) is None
    assert check_call(CoachCall("defense", "cover2"), s) == "It's your offense's call."
    assert check_call(CoachCall("offense", "cover2"), s) == "Unknown offense play: cover2."
    assert check_call(CoachCall("offense", "smash", "dime"), s)
    assert check_call(CoachCall("offense", "smash", None, True),
                      _situation(clock_running=False)) == "The clock is already stopped."
    defending = _situation(role="defense", possession="away")
    assert check_call(CoachCall("defense", "cover2", "nickel"), defending) is None
    assert check_call(CoachCall("defense", "cover2", None, True), defending) is None
    assert check_call(CoachCall("defense", "cover2", None, True),
                      _situation(role="defense", possession="home")) == "You have no timeouts left."


# ---------- the API ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _next_game(client: TestClient) -> dict:
    return client.get("/api/franchise/next-game").json()


def test_next_game(client: TestClient, franchise):
    body = _next_game(client)
    assert body["game"]["week"] == 1 and body["coaching"] is False
    ids = (body["game"]["home"]["id"], body["game"]["away"]["id"])
    assert franchise.team_id in ids


def test_coaching_a_game(client: TestClient, db: Session, season: Season, franchise):
    game_id = _next_game(client)["game"]["id"]
    assert client.get(f"/api/games/{game_id}/coach").status_code == 404

    state = client.post(f"/api/games/{game_id}/coach").json()
    db.commit()
    assert state["status"] == "in_progress" and state["team"]["id"] == franchise.team_id
    assert state["situation"]["quarter"] == 1 and state["plays"][0]["type"] == "kickoff"
    assert _next_game(client)["coaching"] is True
    # Starting again picks up where we were.
    assert client.post(f"/api/games/{game_id}/coach").json()["calls"] == 0

    # Calls must fit the situation.
    role = state["situation"]["role"]
    wrong = "cover2" if role == "offense" else "smash"
    response = client.post(f"/api/games/{game_id}/coach/call", json={"play": wrong})
    assert response.status_code == 422
    right = "smash" if role == "offense" else "cover2"
    after = client.post(f"/api/games/{game_id}/coach/call", json={"play": right}).json()
    db.commit()
    assert after["calls"] == 1 and after["new_plays"] >= 1
    assert len(after["plays"]) == len(state["plays"]) + after["new_plays"]

    # The AI can take a play, or the drive.
    one = client.post(f"/api/games/{game_id}/coach/auto", json={"scope": "play"}).json()
    assert one["calls"] == 2
    drive = client.post(f"/api/games/{game_id}/coach/auto", json={"scope": "drive"}).json()
    db.commit()
    assert drive["calls"] > 2 and drive["status"] == "in_progress"

    # The week can't be simulated while the game is in progress.
    blocked = client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
    assert blocked.status_code == 409 and "coaching" in blocked.json()["detail"]

    # Hand the rest to the AI: the game is stored like any other.
    final = client.post(f"/api/games/{game_id}/coach/auto", json={"scope": "game"}).json()
    db.commit()
    assert final["status"] == "final" and final["situation"] is None
    detail = client.get(f"/api/games/{game_id}").json()
    assert detail["game"]["status"] == "final"
    assert sum(detail["line_score"]["home"]) == detail["game"]["home_score"]
    assert detail["team_stats"]["home"]["points"] == detail["game"]["home_score"]
    late = client.post(f"/api/games/{game_id}/coach/call", json={"play": "smash"})
    assert late.status_code == 409
    assert client.get(f"/api/games/{game_id}/coach").json()["status"] == "final"
    assert _next_game(client)["game"] is None  # played; the rest of the week is next

    # Simulating the week plays everyone else and leaves the coached game as it was.
    score = (detail["game"]["home_score"], detail["game"]["away_score"])
    result = client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
    db.commit()
    assert result.status_code == 200 and result.json()["season"]["current_week"] == 2
    game = db.get(Game, game_id)
    db.refresh(game)
    assert (game.home_score, game.away_score) == score
    coached = db.scalar(select(CoachedGame).where(CoachedGame.game_id == game_id))
    assert coached.status == "settled"
    week1 = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1)).all()
    assert all(g.status == "final" for g in week1)
    assert _next_game(client)["game"]["week"] == 2


def test_only_the_franchise_next_game_can_be_coached(client: TestClient, db: Session,
                                                     season: Season, franchise):
    other = db.scalars(select(Game).where(
        Game.season_id == season.id, Game.week == 2,
        Game.home_team_id != franchise.team_id, Game.away_team_id != franchise.team_id)).first()
    response = client.post(f"/api/games/{other.id}/coach")
    assert response.status_code == 409 and "next game" in response.json()["detail"]
    assert client.post("/api/games/999999/coach").status_code == 404
    assert client.post("/api/games/999999/coach/call", json={"play": "smash"}).status_code == 404


def test_roster_moves_dont_change_a_game_in_progress(client: TestClient, db: Session,
                                                     franchise):
    game_id = _next_game(client)["game"]["id"]
    before = client.post(f"/api/games/{game_id}/coach").json()
    db.commit()
    # Release the franchise's starting quarterback mid-game.
    roster = client.get(f"/api/teams/{franchise.team_id}/roster").json()
    qb = next(p for p in roster if p["position"] == "QB")
    assert client.post(f"/api/players/{qb['id']}/release").status_code == 200
    db.commit()
    again = client.get(f"/api/games/{game_id}/coach").json()
    assert again["plays"] == before["plays"] and again["situation"] == before["situation"]
