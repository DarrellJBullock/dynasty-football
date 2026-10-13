import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api import auth
from app.api.access import SESSION_COOKIE
from app.config import get_settings
from app.models import (
    Franchise,
    Game,
    League,
    Player,
    Season,
    Team,
    TradeOffer,
    User,
    UserSession,
)
from app.services import accounts, jobs, members
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, make_client, sign_in_as


@pytest.fixture(autouse=True)
def fresh_limits():
    """The sign-in limiters live in the process: start each test with clean counts."""
    auth.by_email.failures.clear()
    auth.by_address.failures.clear()


@pytest.fixture
def intruder(db: Session) -> TestClient:
    """A second account, signed in, with no league of its own."""
    with make_client(db) as client:
        yield sign_in_as(client, db, accounts.sign_up(db, "intruder@example.test", "intruder-pass"))


class TestSigningUpAndIn:
    def test_sign_up_signs_in(self, anonymous: TestClient):
        response = anonymous.post("/api/auth/signup",
                                  json={"email": "  New@Example.TEST ", "password": "long enough"})
        assert response.status_code == 201, response.text
        assert response.json() == {**response.json(), "email": "new@example.test",
                                   "has_league": False}
        cookie = response.headers["set-cookie"]
        assert f"{SESSION_COOKIE}=" in cookie and "HttpOnly" in cookie
        assert "samesite=lax" in cookie.lower() and "Max-Age=2592000" in cookie
        assert anonymous.get("/api/auth/me").json()["email"] == "new@example.test"
        # A new account has no league yet.
        assert anonymous.get("/api/franchise").status_code == 404
        assert anonymous.get("/api/leagues").json() == []

    @pytest.mark.parametrize("email,password,status", [
        ("not-an-email", "long enough", 422),
        ("a@b.test", "short", 422),
        (OWNER_EMAIL.upper(), "long enough", 409),
    ])
    def test_sign_up_rules(self, anonymous: TestClient, email: str, password: str, status: int):
        response = anonymous.post("/api/auth/signup", json={"email": email, "password": password})
        assert response.status_code == status

    def test_sign_in_and_out(self, anonymous: TestClient, db: Session):
        assert anonymous.get("/api/auth/me").status_code == 401
        wrong = anonymous.post("/api/auth/signin",
                               json={"email": OWNER_EMAIL, "password": "not it"})
        assert wrong.status_code == 401
        assert wrong.json()["detail"] == "Wrong email or password."
        assert anonymous.post("/api/auth/signin", json={"email": "nobody@example.test",
                                                         "password": "whatever1"}).json() == \
            wrong.json()  # the same answer, whether or not the account exists

        signed_in = anonymous.post("/api/auth/signin",
                                   json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert signed_in.status_code == 200
        assert signed_in.json()["has_league"] is True
        assert anonymous.get("/api/franchise").status_code == 200

        assert anonymous.post("/api/auth/signout").status_code == 204
        assert anonymous.get("/api/franchise").status_code == 401
        assert db.scalar(select(func.count(UserSession.id))) == 0

    def test_repeated_failures_are_refused_for_a_while(self, anonymous: TestClient):
        bad = {"email": OWNER_EMAIL, "password": "guess-guess"}
        for _ in range(10):
            assert anonymous.post("/api/auth/signin", json=bad).status_code == 401
        good = {"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        assert anonymous.post("/api/auth/signin", json=good).status_code == 429
        # Another account from elsewhere isn't affected.
        assert anonymous.post("/api/auth/signin", json={"email": "other@example.test",
                                                         "password": "x" * 8},
                              headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 401

    def test_the_limiter_forgets_after_its_window(self):
        limiter = accounts.RateLimiter(limit=2, window=60)
        limiter.failed("k", now=0)
        limiter.failed("k", now=1)
        assert limiter.blocked("k", now=30)
        assert not limiter.blocked("k", now=62)

    def test_the_first_account_takes_over_leagues_from_before_accounts(self, db: Session,
                                                                      league: League):
        db.execute(update(League).values(user_id=None))
        db.execute(delete(UserSession))
        db.execute(delete(User))
        first = accounts.sign_up(db, "first@example.test", "first-password")
        assert league.user_id is None or db.get(League, league.id).user_id == first.id
        db.refresh(league)
        assert league.user_id == first.id
        second = accounts.sign_up(db, "second@example.test", "second-password")
        assert db.scalar(select(func.count(League.id)).where(League.user_id == second.id)) == 0


class TestSessions:
    def test_expired_sessions_sign_out(self, client: TestClient, db: Session):
        db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        assert client.get("/api/auth/me").status_code == 401
        assert db.scalar(select(func.count(UserSession.id))) == 0

    def test_sessions_are_extended_as_they_are_used(self, client: TestClient, db: Session):
        soon = datetime.now(UTC) + timedelta(days=3)
        db.execute(update(UserSession).values(expires_at=soon))
        assert client.get("/api/auth/me").status_code == 200
        expires = db.scalar(select(UserSession.expires_at))
        assert accounts._aware(expires) > datetime.now(UTC) + timedelta(days=29)

    def test_only_a_hash_of_the_token_is_stored(self, client: TestClient, db: Session):
        token = client.cookies.get(SESSION_COOKIE)
        stored = db.scalar(select(UserSession.token_hash))
        assert token and stored != token and re.fullmatch(r"[0-9a-f]{64}", stored)


class TestTheAccount:
    def test_changing_the_password_signs_out_other_browsers(self, client: TestClient,
                                                            db: Session, owner: User):
        with make_client(db) as other:
            sign_in_as(other, db, owner)
            wrong = client.put("/api/auth/password", json={"current_password": "nope-nope",
                                                            "new_password": "brand-new-pass"})
            assert wrong.status_code == 403
            assert client.put("/api/auth/password", json={
                "current_password": OWNER_PASSWORD, "new_password": "brand-new-pass"}
            ).status_code == 204
            assert client.get("/api/auth/me").status_code == 200
            assert other.get("/api/auth/me").status_code == 401
        assert accounts.authenticate(db, OWNER_EMAIL, "brand-new-pass").id == owner.id

    def test_deleting_the_account_deletes_its_leagues(self, client: TestClient, db: Session,
                                                      owner: User):
        spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        client.post("/api/leagues", json=spec.json())
        assert client.request("DELETE", "/api/auth/account",
                              json={"password": "wrong-one"}).status_code == 403
        response = client.request("DELETE", "/api/auth/account", json={"password": OWNER_PASSWORD})
        assert response.status_code == 204
        assert db.scalar(select(func.count(League.id))) == 0
        assert db.scalar(select(func.count(Player.id))) == 0
        assert db.get(User, owner.id) is None
        assert client.get("/api/auth/me").status_code == 401

    def test_admin_password_reset(self, db: Session, owner: User):
        accounts.start_session(db, owner)
        accounts.set_password(db, OWNER_EMAIL.upper(), "reset-by-admin")
        assert accounts.authenticate(db, OWNER_EMAIL, "reset-by-admin").id == owner.id
        assert db.scalar(select(func.count(UserSession.id))) == 0
        with pytest.raises(accounts.AuthError):
            accounts.set_password(db, "nobody@example.test", "whatever-1")

    def test_seeding_gives_the_league_to_the_dev_account(self, db: Session):
        user = accounts.ensure_user(db, "dev@example.test", "dev-password")
        assert accounts.ensure_user(db, "DEV@example.test", "changed-password").id == user.id
        assert accounts.authenticate(db, "dev@example.test", "changed-password").id == user.id


def _an_offer(db: Session, league: League, season: Season, franchise: Franchise) -> TradeOffer:
    other = db.scalar(select(Team.id).where(Team.league_id == league.id,
                                            Team.id != franchise.team_id))
    offer = TradeOffer(league_id=league.id, season_id=season.id, from_team_id=franchise.team_id,
                       to_team_id=other, send=[], receive=[],
                       expires_at=datetime.now(UTC) + timedelta(days=1))
    db.add(offer)
    db.flush()
    return offer


class TestLeaguesBelongToTheirOwner:
    def test_each_account_has_its_own_leagues_and_active_franchise(
            self, client: TestClient, intruder: TestClient, franchise: Franchise):
        assert intruder.get("/api/franchises").json() == []
        spec = intruder.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        mine = intruder.post("/api/leagues", json=spec.json())
        assert mine.status_code == 201
        assert intruder.get("/api/franchise").json()["id"] == mine.json()["id"]
        assert [f["id"] for f in intruder.get("/api/franchises").json()] == [mine.json()["id"]]
        # The owner's active franchise didn't change, and they can't see the new league.
        assert client.get("/api/franchise").json()["id"] == franchise.id
        assert mine.json()["league"]["id"] not in [
            league["id"] for league in client.get("/api/leagues").json()]
        assert client.get(f"/api/leagues/{mine.json()['league']['id']}").status_code == 404

    def test_every_route_into_someone_elses_league_is_not_found(
            self, client: TestClient, intruder: TestClient, db: Session, league: League,
            franchise: Franchise, owner: User):
        season = db.scalar(select(Season).where(Season.league_id == league.id))
        ids = {
            "league_id": league.id, "season_id": season.id, "team_id": franchise.team_id,
            "player_id": db.scalar(select(Player.id).where(Player.team_id == franchise.team_id)),
            "game_id": db.scalar(select(Game.id).where(Game.season_id == season.id)),
            "franchise_id": franchise.id,
            "job_id": jobs.enqueue(db, league, "sim_regular_season").id,
            "invite_id": members.create_invite(db, league, owner)[0].id,
            "member_id": members.member(db, league.id, owner).id,
            "offer_id": _an_offer(db, league, season, franchise).id,
            "slot": "QB", "fmt": "csv", "token": "not-a-shared-link",
        }
        unscoped = set()
        checked = 0
        for path, methods in client.app.openapi()["paths"].items():
            names = re.findall(r"{(\w+)}", path)
            if not any(name.endswith("_id") for name in names):
                unscoped |= {f"{method.upper()} {path}" for method in methods}
                continue
            url = re.sub(r"{(\w+)}", lambda m: str(ids[m.group(1)]), path)
            for method in methods:
                response = intruder.request(method.upper(), url, json={})
                assert response.status_code == 404, f"{method.upper()} {path}: {response.text}"
                checked += 1
        assert checked > 50
        # Routes without ids answer for the signed-in user only (or are the same for all).
        assert unscoped == {
            "GET /api/health", "GET /api/ready", "POST /api/auth/signup", "POST /api/auth/signin",
            "POST /api/auth/forgot", "POST /api/auth/reset",
            "POST /api/auth/signout", "GET /api/auth/me", "PUT /api/auth/password",
            "PUT /api/auth/profile", "POST /api/invites/preview", "POST /api/invites/join",
            "GET /api/notifications", "GET /api/notifications/unread",
            "POST /api/notifications/read",
            # The read-only public link: anyone with its token (tests/test_sharing.py).
            "GET /api/public/{token}", "GET /api/public/{token}/standings",
            "GET /api/public/{token}/schedule", "GET /api/public/{token}/playoffs",
            "GET /api/public/{token}/leaders", "GET /api/public/{token}/team-stats",
            "GET /api/public/{token}/history",
            "DELETE /api/auth/account", "GET /api/franchise", "GET /api/franchise/dashboard",
            "GET /api/franchise/next-game", "GET /api/franchises", "GET /api/leagues",
            "POST /api/leagues", "GET /api/leagues/template", "GET /api/playbook",
            "GET /api/roster-import/template.{fmt}",
        }

    def test_signed_out_visitors_get_nothing(self, anonymous: TestClient, league: League):
        for url in ("/api/franchise", "/api/leagues", f"/api/leagues/{league.id}/standings",
                    "/api/playbook"):
            assert anonymous.get(url).status_code == 401
        assert anonymous.post(f"/api/leagues/{league.id}/jobs",
                              json={"kind": "sim_playoffs"}).status_code == 401
        assert anonymous.get("/api/health").status_code == 200

    def test_a_league_limit_per_account(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_leagues", 1)
        spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        response = client.post("/api/leagues", json=spec.json())
        assert response.status_code == 409
        assert "up to 1 leagues" in response.json()["detail"]


def test_changes_from_other_sites_are_refused(client: TestClient, franchise: Franchise):
    url = f"/api/teams/{franchise.team_id}/depth-chart"
    assert client.delete(url, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.delete(url, headers={"Origin": "http://localhost:3000"}).status_code == 200
    # Reads are fine from anywhere (the cookie's SameSite and CORS keep them private).
    assert client.get(url, headers={"Origin": "https://evil.example"}).status_code == 200
