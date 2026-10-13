"""Leagues with friends, part 1: members, roles and invites
(docs/design/leagues-with-friends.md)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.access import WRITES
from app.models import (
    Franchise,
    Game,
    League,
    LeagueInvite,
    LeagueMember,
    Player,
    Season,
    Team,
    User,
)
from app.services import accounts, jobs, members
from tests.conftest import OWNER_PASSWORD, make_client, sign_in_as


def _client_for(db: Session, email: str) -> tuple[User, TestClient]:
    user = accounts.sign_up(db, email, "friend-password")
    return user, sign_in_as(make_client(db), db, user)


@pytest.fixture
def friend(db: Session) -> tuple[User, TestClient]:
    """A second account, signed in, not (yet) in the sample league."""
    user, client = _client_for(db, "friend@example.test")
    with client:
        yield user, client


def _invite(client: TestClient, league: League) -> str:
    response = client.post(f"/api/leagues/{league.id}/invites")
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _join(client: TestClient, token: str, team_id: int):
    return client.post("/api/invites/join", json={"token": token, "team_id": team_id})


def _open_team(db: Session, league: League, franchise: Franchise) -> Team:
    return db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))


@pytest.fixture
def joined(db: Session, client: TestClient, friend, league: League,
           franchise: Franchise) -> tuple[User, TestClient, Team]:
    """The friend, a manager running another team in the sample league."""
    user, other = friend
    team = _open_team(db, league, franchise)
    assert _join(other, _invite(client, league), team.id).status_code == 201
    return user, other, team


class TestTheCreator:
    def test_is_the_commissioner_and_runs_their_franchise(self, db: Session, owner: User,
                                                         league: League,
                                                         franchise: Franchise):
        assert members.is_commissioner(db, league.id, owner)
        assert franchise.user_id == owner.id
        assert members.user_team_id(db, league.id, owner) == franchise.team_id

    def test_of_a_new_league_too(self, client: TestClient, db: Session, owner: User):
        spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        made = client.post("/api/leagues", json=spec.json()).json()
        assert members.is_commissioner(db, made["league"]["id"], owner)
        roster = client.get(f"/api/leagues/{made['league']['id']}/members").json()
        assert [(m["role"], m["team"]["id"], m["is_you"]) for m in roster["members"]] == [
            ("commissioner", made["team"]["id"], True)]


class TestInvites:
    def test_a_friend_joins_with_a_link_and_picks_an_open_team(
            self, db: Session, client: TestClient, friend, league: League,
            franchise: Franchise):
        user, other = friend
        token = _invite(client, league)
        assert db.scalar(select(LeagueInvite.token_hash)) != token  # (only the hash is kept)
        preview = other.post("/api/invites/preview", json={"token": token}).json()
        assert preview["league"]["id"] == league.id and not preview["already_member"]
        assert preview["commissioner"] == "owner"  # (the email's first part, until a name's set)
        assert franchise.team_id not in [t["id"] for t in preview["open_teams"]]
        team = _open_team(db, league, franchise)
        joined = _join(other, token, team.id)
        assert joined.status_code == 201
        assert joined.json()["team"]["id"] == team.id
        # Their franchise is active: the dashboard, roster and so on are their team's.
        assert other.get("/api/franchise").json()["team"]["id"] == team.id
        assert client.get("/api/franchise").json()["team"]["id"] == franchise.team_id
        assert other.get("/api/auth/me").json()["has_league"]
        roster = client.get(f"/api/leagues/{league.id}/members").json()
        assert [(m["display_name"], m["role"]) for m in roster["members"]] == [
            ("owner", "commissioner"), ("friend", "manager")]
        assert team.id not in [t["id"] for t in roster["open_teams"]]
        assert db.get(LeagueInvite, roster["invites"][0]["id"]).uses == 1

    def test_a_taken_team_or_a_second_team_is_refused(self, db: Session, client: TestClient,
                                                      joined, league: League,
                                                      franchise: Franchise):
        _user, other, team = joined
        token = _invite(client, league)
        third, stranger = _client_for(db, "third@example.test")
        with stranger:
            assert _join(stranger, token, franchise.team_id).status_code == 409
            assert _join(stranger, token, team.id).status_code == 409
        spare = db.scalar(select(Team.id).where(Team.league_id == league.id,
                                                Team.id.not_in([team.id, franchise.team_id])))
        assert _join(other, token, spare).status_code == 409  # (one team each)

    def test_expired_revoked_and_wrong_links_are_not_found(self, db: Session,
                                                          client: TestClient, friend,
                                                          league: League):
        _user, other = friend
        preview = "/api/invites/preview"
        assert other.post(preview, json={"token": "not-a-real-token"}).status_code == 404
        token = _invite(client, league)
        db.scalar(select(LeagueInvite)).expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        assert other.post(preview, json={"token": token}).status_code == 404
        token = _invite(client, league)
        invite_id = client.get(f"/api/leagues/{league.id}/members").json()["invites"][0]["id"]
        assert client.delete(f"/api/leagues/{league.id}/invites/{invite_id}").status_code == 204
        assert other.post("/api/invites/preview", json={"token": token}).status_code == 404
        assert client.get(f"/api/leagues/{league.id}/members").json()["invites"] == []

    def test_only_commissioners_make_links_or_see_them(self, client: TestClient, joined,
                                                      league: League):
        _user, other, _team = joined
        assert other.post(f"/api/leagues/{league.id}/invites").status_code == 403
        assert other.get(f"/api/leagues/{league.id}/members").json()["invites"] == []


class TestWhoMayDoWhat:
    def test_a_manager_runs_their_team_and_only_theirs(self, db: Session, client: TestClient,
                                                      joined, league: League,
                                                      franchise: Franchise):
        _user, other, team = joined
        assert other.delete(f"/api/teams/{team.id}/depth-chart").status_code == 200
        refused = other.delete(f"/api/teams/{franchise.team_id}/depth-chart")
        assert refused.status_code == 403
        theirs = db.scalar(select(Player.id).where(Player.team_id == franchise.team_id))
        assert other.post(f"/api/players/{theirs}/release").status_code == 403
        # They see the whole league.
        assert other.get(f"/api/teams/{franchise.team_id}/depth-chart").status_code == 200
        assert other.get(f"/api/leagues/{league.id}/standings").status_code == 200

    def test_the_commissioner_runs_the_season_and_can_stand_in(
            self, db: Session, client: TestClient, joined, league: League):
        _user, other, team = joined
        season = db.scalar(select(Season).where(Season.league_id == league.id))
        assert other.post(f"/api/seasons/{season.id}/simulate",
                          json={"until": "next_week"}).status_code == 403
        assert other.post(f"/api/leagues/{league.id}/jobs",
                          json={"kind": "sim_regular_season"}).status_code == 403
        assert other.request("DELETE", f"/api/leagues/{league.id}").status_code == 403
        assert client.delete(f"/api/teams/{team.id}/depth-chart").status_code == 200
        plan = client.get(f"/api/teams/{team.id}/game-plan").json()
        assert client.put(f"/api/teams/{team.id}/game-plan", json={
            key: plan[key] for key in ("offense", "defense", "tendencies")}).status_code == 200

    def test_coaching_is_for_your_own_games(self, db: Session, client: TestClient, joined,
                                            league: League, franchise: Franchise):
        _user, other, team = joined
        season = db.scalar(select(Season).where(Season.league_id == league.id))
        mine = [franchise.team_id]
        neither = db.scalar(select(Game).where(
            Game.season_id == season.id, Game.home_team_id.not_in(mine + [team.id]),
            Game.away_team_id.not_in(mine + [team.id])))
        assert other.post(f"/api/games/{neither.id}/coach").status_code == 403
        owners_game = db.scalar(select(Game).where(
            Game.season_id == season.id, Game.home_team_id == franchise.team_id,
            Game.away_team_id != team.id))
        assert other.post(f"/api/games/{owners_game.id}/coach").status_code == 403

    def test_a_member_without_a_team_cant_trade_or_draft(self, db: Session, client: TestClient,
                                                         friend, league: League):
        user, other = friend
        members.add(db, league, user, "manager")
        db.commit()
        refused = other.post(f"/api/leagues/{league.id}/trades/evaluate", json={})
        assert refused.status_code == 403
        assert "don't run a team" in refused.json()["detail"]

    def test_every_change_route_has_a_rule(self, client: TestClient):
        """A new route that changes a league must say who may make it (api/access.py)."""
        unruled = []
        for path, methods in client.app.openapi()["paths"].items():
            names = re.findall(r"{(\w+)}", path)
            for method in methods:
                if method.upper() == "GET" or not any(n.endswith("_id") for n in names):
                    continue
                if f"{method.upper()} {path}" not in WRITES:
                    unruled.append(f"{method.upper()} {path}")
        assert unruled == []
        assert all(f"{m} {p}".split(" ", 1)[1] in client.app.openapi()["paths"]
                   for m, p in (key.split(" ", 1) for key in WRITES))


class TestLeaving:
    def test_a_manager_leaves_and_their_team_goes_back_to_the_ai(
            self, db: Session, client: TestClient, joined, league: League):
        user, other, team = joined
        mine = members.member(db, league.id, user)
        assert other.delete(f"/api/leagues/{league.id}/members/{mine.id}").status_code == 204
        assert team.id not in members.human_team_ids(db, league.id)
        assert other.get(f"/api/leagues/{league.id}").status_code == 404
        assert other.get("/api/franchise").status_code == 404

    def test_the_commissioner_removes_a_manager_but_a_manager_cant(
            self, db: Session, client: TestClient, joined, league: League, owner: User):
        user, other, _team = joined
        commissioner = members.member(db, league.id, owner)
        assert other.delete(
            f"/api/leagues/{league.id}/members/{commissioner.id}").status_code == 403
        manager = members.member(db, league.id, user)
        assert client.delete(
            f"/api/leagues/{league.id}/members/{manager.id}").status_code == 204
        assert members.member(db, league.id, user) is None

    def test_the_last_commissioner_hands_over_first(self, db: Session, client: TestClient,
                                                    joined, league: League, owner: User):
        user, _other, _team = joined
        commissioner = members.member(db, league.id, owner)
        url = f"/api/leagues/{league.id}/members"
        assert client.delete(f"{url}/{commissioner.id}").status_code == 409
        assert client.patch(f"{url}/{commissioner.id}",
                            json={"role": "manager"}).status_code == 409
        manager = members.member(db, league.id, user)
        promoted = client.patch(f"{url}/{manager.id}", json={"role": "commissioner"})
        assert promoted.status_code == 200
        assert client.delete(f"{url}/{commissioner.id}").status_code == 204

    def test_deleting_an_account_leaves_shared_leagues_to_the_others(
            self, db: Session, client: TestClient, joined, league: League, owner: User):
        user, other, _team = joined
        accounts.delete_account(db, owner, OWNER_PASSWORD)
        db.flush()
        assert db.get(League, league.id) is not None
        assert members.is_commissioner(db, league.id, user)
        assert db.get(League, league.id).user_id == user.id
        assert db.scalar(select(func.count(Player.id)).where(Player.league_id == league.id))


class TestDisplayNames:
    def test_members_see_a_name_not_an_email(self, client: TestClient, joined, league: League):
        _user, other, _team = joined
        assert other.put("/api/auth/profile",
                         json={"display_name": "  Coach   Sam "}).json()["display_name"] == (
            "Coach Sam")
        assert other.put("/api/auth/profile", json={"display_name": "   "}).status_code == 422
        names = [m["display_name"] for m in
                 client.get(f"/api/leagues/{league.id}/members").json()["members"]]
        assert "Coach Sam" in names
        assert "friend@example.test" not in str(
            client.get(f"/api/leagues/{league.id}/members").json())


def test_a_running_simulation_holds_joins(db: Session, client: TestClient, friend,
                                         league: League, franchise: Franchise):
    _user, other = friend
    token = _invite(client, league)
    jobs.enqueue(db, league, "sim_regular_season")
    assert _join(other, token, _open_team(db, league, franchise).id).status_code == 409


def test_members_rows_go_with_the_league(db: Session, client: TestClient, joined,
                                         league: League):
    from app.services.leagues import delete_league

    delete_league(db, league)
    db.flush()
    assert db.scalar(select(func.count(LeagueMember.id))) == 0
    assert db.scalar(select(func.count(LeagueInvite.id))) == 0
