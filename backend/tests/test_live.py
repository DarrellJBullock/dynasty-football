"""Milestone 13, part 2: playing head-to-head (docs/design/head-to-head-and-commissioner.md §3)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Franchise, Game, League, LiveGame, Notification, Season, Team, User
from app.schemas import SimulateRequest
from app.services import accounts, live, members
from app.services import season as season_service
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def friend(db: Session, owner: User, league: League,
           franchise: Franchise) -> tuple[User, TestClient, Team]:
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    user.display_name = "Robin"
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user), team


@pytest.fixture
def matchup(db: Session, friend, season: Season, franchise: Franchise) -> Game:
    """This week's game: our team at home against the friend's."""
    _user, _client, team = friend
    for existing in db.scalars(select(Game).where(
            Game.season_id == season.id, Game.week == 1,
            (Game.home_team_id.in_([franchise.team_id, team.id]))
            | (Game.away_team_id.in_([franchise.team_id, team.id])))):
        existing.week = 99  # (so this is each team's game this week)
    game = Game(season_id=season.id, week=1, stage="regular", status="scheduled",
                home_team_id=franchise.team_id, away_team_id=team.id)
    db.add(game)
    db.commit()
    return game


def _url(game: Game, path: str = "") -> str:
    return f"/api/games/{game.id}/live{path}"


def _started(client: TestClient, other: TestClient, game: Game, clock=None) -> dict:
    assert client.post(_url(game), json={"clock_seconds": clock}).status_code == 201
    accepted = other.post(_url(game, "/accept"))
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


def _my_call(client: TestClient, game: Game) -> dict:
    """Take the AI's suggestion for whatever the game waits on from this coach."""
    state = client.get(_url(game)).json()
    s = state["situation"]
    body = {"play": s["suggestion"]}
    if s["role"] == "defense":
        body["package"] = s["suggested_package"]
    response = client.post(_url(game, "/call"), json=body)
    assert response.status_code == 200, response.text
    return response.json()


class TestAgreeing:
    def test_an_offer_then_a_yes(self, db: Session, client: TestClient, friend, matchup: Game,
                                 owner: User):
        user, other, _team = friend
        offered = client.post(_url(matchup), json={"clock_seconds": None})
        assert offered.status_code == 201, offered.text
        assert offered.json()["status"] == "proposed" and offered.json()["proposed_by_you"]
        assert db.scalar(select(Notification.title).where(
            Notification.user_id == user.id, Notification.kind == "live")).endswith(
            "want to play this week's game live")
        assert client.post(_url(matchup, "/accept")).status_code == 403  # (not your own)
        state = other.post(_url(matchup, "/accept")).json()
        assert state["status"] == "in_progress" and state["side"] == "away"
        assert state["managers"] == {"home": "owner", "away": "Robin"}
        assert "Your live game is on" in db.scalars(select(Notification.title).where(
            Notification.user_id == owner.id, Notification.kind == "live")).all()

    def test_a_no_and_the_game_is_simulated_as_ever(self, db: Session, client: TestClient,
                                                   friend, matchup: Game, season: Season):
        _user, other, _team = friend
        client.post(_url(matchup), json={})
        assert other.post(_url(matchup, "/decline")).json()["status"] == "declined"
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        assert matchup.status == "final"
        assert client.post(_url(matchup), json={}).status_code == 409  # (played)

    def test_only_for_two_members_this_week(self, db: Session, client: TestClient,
                                            season: Season, franchise: Franchise, friend,
                                            matchup: Game):
        ai_game = db.scalar(select(Game).where(
            Game.season_id == season.id, Game.week == 2,
            (Game.home_team_id == franchise.team_id) | (Game.away_team_id == franchise.team_id)))
        refused = client.post(_url(ai_game), json={})
        assert refused.status_code == 409 and "between two members" in refused.json()["detail"]
        assert client.post(_url(matchup), json={"clock_seconds": 7}).status_code == 422


class TestPlaying:
    def test_each_snap_waits_for_both_calls_made_blind(self, client: TestClient, friend,
                                                       matchup: Game):
        _user, other, _team = friend
        _started(client, other, matchup)
        # The kickoff: one coach's decision.
        kicker = client if client.get(_url(matchup)).json()["situation"] else other
        _my_call(kicker, matchup)
        mine = client.get(_url(matchup)).json()
        theirs = other.get(_url(matchup)).json()
        assert mine["situation"] and theirs["situation"]  # (both call this snap)
        assert {mine["situation"]["role"], theirs["situation"]["role"]} == {"offense", "defense"}
        plays = len(mine["plays"])
        after_mine = _my_call(client, matchup)
        assert after_mine["situation"] is None  # (waiting, blind, on the other coach)
        assert after_mine["waiting_on"] == [matchup.away_team.abbreviation]
        assert len(after_mine["plays"]) == plays  # (nothing plays until both have called)
        assert client.post(_url(matchup, "/call"), json={"play": "smash"}).status_code == 409
        after_theirs = _my_call(other, matchup)
        assert len(after_theirs["plays"]) > plays and after_theirs["new_plays"] >= 1

    def test_your_call_is_told(self, db: Session, client: TestClient, friend, matchup: Game):
        user, other, _team = friend
        _started(client, other, matchup)
        kicker = client if client.get(_url(matchup)).json()["situation"] else other
        _my_call(kicker, matchup)
        _my_call(client, matchup)
        _my_call(other, matchup)
        assert "Your call" in db.scalars(select(Notification.title).where(
            Notification.user_id == user.id, Notification.kind == "live")).all()

    def test_both_hand_it_to_the_ai_and_it_finishes(self, db: Session, client: TestClient,
                                                     friend, matchup: Game):
        _user, other, _team = friend
        _started(client, other, matchup)
        client.post(_url(matchup, "/auto"), json={"scope": "game"})
        final = other.post(_url(matchup, "/auto"), json={"scope": "game"}).json()
        assert final["status"] == "final" and matchup.status == "final"
        assert final["plays"] and matchup.home_score is not None

    def test_a_call_clock_has_the_ai_call_for_whoever_ran_out(self, db: Session,
                                                              client: TestClient, friend,
                                                              matchup: Game):
        _user, other, _team = friend
        state = _started(client, other, matchup, clock=120)
        assert state["deadline"] is not None
        found = live.live_game(db, matchup)
        plays = len(live.live_plays(found))
        assert not live.settle_clock(db, found, datetime.now(UTC) + timedelta(seconds=60))
        assert live.settle_clock(db, found, datetime.now(UTC) + timedelta(minutes=5))
        assert len(live.live_plays(found)) > plays

    def test_the_3d_playback_follows_the_game(self, client: TestClient, friend, matchup: Game):
        _user, other, _team = friend
        _started(client, other, matchup)
        client.post(_url(matchup, "/auto"), json={"scope": "drive"})
        other.post(_url(matchup, "/auto"), json={"scope": "drive"})
        playback = client.get(f"/api/games/{matchup.id}/playback").json()
        assert len(playback["plays"]) == len(client.get(_url(matchup)).json()["plays"])


def test_the_week_finishes_an_unfinished_live_game(db: Session, client: TestClient, friend,
                                                   matchup: Game, season: Season):
    _user, other, _team = friend
    _started(client, other, matchup)
    kicker = client if client.get(_url(matchup)).json()["situation"] else other
    _my_call(kicker, matchup)
    season_service.simulate(db, season, SimulateRequest(until="next_week"))
    found = live.live_game(db, matchup)
    assert found.status == "settled" and matchup.status == "final"
    assert found.calls[("home" if kicker is client else "away")]  # (its calls stood)
    others = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1)).all()
    assert all(g.status == "final" for g in others)


def test_watchers_see_the_game_but_never_a_call(db: Session, client: TestClient, friend,
                                                matchup: Game, league: League):
    _user, other, _team = friend
    _started(client, other, matchup)
    watcher = accounts.sign_up(db, "watcher@example.test", "watcher-password")
    members.add(db, league, watcher, "manager")
    db.commit()
    with make_client(db) as third:
        sign_in_as(third, db, watcher)
        view = third.get(_url(matchup)).json()
        assert view["side"] is None and view["situation"] is None
        assert set(view["waiting_on"]) <= {matchup.home_team.abbreviation,
                                           matchup.away_team.abbreviation}
        assert third.post(_url(matchup, "/call"), json={"play": "smash"}).status_code == 403


def test_live_games_go_with_the_league(db: Session, client: TestClient, friend, matchup: Game,
                                       league: League):
    from app.services.leagues import delete_league

    _user, other, _team = friend
    _started(client, other, matchup)
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(LiveGame.id)) is None
