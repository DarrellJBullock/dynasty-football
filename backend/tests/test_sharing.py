"""Leagues with friends, part 5: the read-only public link and the league export
(docs/design/leagues-with-friends.md §7)."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Franchise, Game, League, Player, Season, Team, User
from app.observability import loggable_path, scrub
from app.schemas import SimulateRequest
from app.services import accounts, members, sharing
from app.services import season as season_service
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def friend(db: Session, owner: User, league: League,
           franchise: Franchise) -> tuple[User, TestClient]:
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user)


def _share(client: TestClient, league: League) -> str:
    response = client.post(f"/api/leagues/{league.id}/share")
    assert response.status_code == 201, response.text
    return response.json()["token"]


class TestThePublicLink:
    def test_anyone_with_it_sees_the_league_without_an_account(
            self, db: Session, client: TestClient, anonymous: TestClient, league: League,
            season: Season):
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        db.commit()
        token = _share(client, league)
        assert db.get(League, league.id).share_token_hash != token  # (only its hash)
        base = f"/api/public/{token}"
        home = anonymous.get(base).json()
        assert home["league"]["id"] == league.id and len(home["teams"]) == len(league.teams)
        game = db.scalar(select(Game).where(Game.season_id == season.id,
                                            Game.status == "final"))
        for path in ("/standings", "/schedule?week=1", "/playoffs", f"/games/{game.id}",
                     f"/games/{game.id}/playback", "/leaders", "/team-stats", "/history"):
            response = anonymous.get(base + path)
            assert response.status_code == 200, (path, response.text)
            assert "salary" not in response.text, path  # (never contracts)

    def test_only_its_own_league_s_games(self, db: Session, client: TestClient,
                                         anonymous: TestClient, league: League):
        token = _share(client, league)
        spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        other = client.post("/api/leagues", json=spec.json()).json()["league"]["id"]
        elsewhere = db.scalar(select(Game.id).join(Season).where(Season.league_id == other))
        assert anonymous.get(f"/api/public/{token}/games/{elsewhere}").status_code == 404

    def test_a_new_link_replaces_the_old_and_revoking_stops_it(
            self, client: TestClient, anonymous: TestClient, league: League):
        first = _share(client, league)
        second = _share(client, league)
        assert anonymous.get(f"/api/public/{first}").status_code == 404
        assert anonymous.get(f"/api/public/{second}").status_code == 200
        assert client.get(f"/api/leagues/{league.id}/members").json()["shared_at"]
        assert client.delete(f"/api/leagues/{league.id}/share").status_code == 204
        assert anonymous.get(f"/api/public/{second}").status_code == 404
        assert client.get(f"/api/leagues/{league.id}/members").json()["shared_at"] is None
        assert anonymous.get("/api/public/made-up").status_code == 404

    def test_only_a_commissioner_shares(self, friend, league: League):
        _user, other = friend
        assert other.post(f"/api/leagues/{league.id}/share").status_code == 403
        assert other.delete(f"/api/leagues/{league.id}/share").status_code == 403

    def test_its_token_is_never_logged(self, client: TestClient, anonymous: TestClient,
                                       league: League, caplog):
        token = _share(client, league)
        with caplog.at_level(logging.INFO, logger="app.request"):
            anonymous.get(f"/api/public/{token}/standings")
        mine = [r for r in caplog.records if r.name == "app.request"]
        assert mine and not any(token in r.getMessage() for r in mine)
        assert loggable_path(f"/api/public/{token}/games/3") == "/api/public/{token}/games/3"
        event = scrub({"request": {"url": f"https://x.example/api/public/{token}?week=2"}})
        assert token not in event["request"]["url"]


class TestTheExport:
    def test_a_member_downloads_the_whole_league(self, db: Session, client: TestClient,
                                                 friend, league: League, season: Season):
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        db.commit()
        _user, other = friend
        response = other.get(f"/api/leagues/{league.id}/export")
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("attachment; filename=")
        data = json.loads(response.content)
        assert data["format"] == sharing.EXPORT_FORMAT and data["version"] == 1
        assert data["league"]["name"] == league.name
        assert len(data["teams"]) == len(league.teams)
        players = db.scalars(select(Player.id).where(Player.league_id == league.id)).all()
        assert len(data["players"]) == len(players)
        assert len(data["player_ratings"]) == len(players)
        assert data["contracts"] and data["games"] and data["team_game_stats"]
        assert {g["status"] for g in data["games"]} >= {"final", "scheduled"}
        # Nothing private: no accounts, emails, members or tokens; no big logs.
        text = response.text
        for private in ("friend@example.test", "owner@example.test", "user_id",
                        "share_token_hash", "play_log", "offseason_log"):
            assert private not in text, private

    def test_strangers_can_t(self, db: Session, league: League):
        stranger = accounts.sign_up(db, "stranger@example.test", "stranger-pass")
        db.commit()
        with make_client(db) as client:
            sign_in_as(client, db, stranger)
            assert client.get(f"/api/leagues/{league.id}/export").status_code == 404
