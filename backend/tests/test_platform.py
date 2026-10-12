import json
import logging
import re
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.policy import default as email_policy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.api import auth
from app.config import get_settings
from app.models import PasswordReset, UserSession
from app.observability import JsonFormatter, init_sentry, request_id, scrub
from app.services import accounts
from app.services import email as email_service
from app.services.health import expected_revision
from tests.conftest import OWNER_EMAIL


@pytest.fixture(autouse=True)
def fresh_limits():
    auth.resets.failures.clear()


@pytest.fixture
def outbox(tmp_path: Path, monkeypatch) -> Path:
    """Emails land here as files instead of going out."""
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    monkeypatch.setattr(get_settings(), "email_outbox", str(tmp_path))
    monkeypatch.setattr(get_settings(), "site_url", "https://dynasty.example")
    return tmp_path


def _emails(outbox: Path):
    return [message_from_bytes(path.read_bytes(), policy=email_policy)
            for path in sorted(outbox.glob("*.eml"))]


class TestHealth:
    def test_liveness_needs_no_sign_in(self, anonymous: TestClient):
        assert anonymous.get("/api/health").json() == {"status": "ok"}

    def test_ready_once_the_schema_is_current(self, anonymous: TestClient, db: Session):
        # The test database is built without migrations, so it isn't stamped yet.
        response = anonymous.get("/api/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "migrating"
        db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        db.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": expected_revision()})
        response = anonymous.get("/api/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "revision": expected_revision()}


class TestRequestIdsAndLogs:
    def test_every_response_carries_a_request_id(self, client: TestClient):
        given = client.get("/api/franchise", headers={"X-Request-ID": "web-1234"})
        assert given.headers["X-Request-ID"] == "web-1234"
        made = client.get("/api/franchise", headers={"X-Request-ID": "not ok!"})
        assert re.fullmatch(r"[0-9a-f]{32}", made.headers["X-Request-ID"])

    def test_each_request_is_logged_with_its_route_and_user(self, client: TestClient,
                                                             owner, caplog):
        with caplog.at_level(logging.INFO, logger="app.request"):
            client.get(f"/api/players/{_a_player(client)}", headers={"X-Request-ID": "abc-1"})
        record = [r for r in caplog.records if r.name == "app.request"][-1]
        assert (record.route, record.status, record.user_id) == ("/api/players/{player_id}", 200,
                                                                owner.id)
        assert record.duration_ms >= 0

    def test_json_log_lines(self):
        record = logging.LogRecord("app.jobs", logging.INFO, "", 0, "job %s queued", (7,), None)
        record.job_id = 7
        token = request_id.set("abc-1")
        try:
            line = json.loads(JsonFormatter().format(record))
        finally:
            request_id.reset(token)
        assert line == {**line, "level": "info", "logger": "app.jobs", "message": "job 7 queued",
                        "request_id": "abc-1", "job_id": 7}


def _a_player(client: TestClient) -> int:
    team = client.get("/api/franchise").json()["team"]["id"]
    return client.get(f"/api/teams/{team}/roster").json()[0]["id"]


class TestErrorReports:
    def test_off_without_a_dsn(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "sentry_dsn", None)
        assert init_sentry("api") is False

    def test_reports_are_scrubbed(self):
        event = scrub({
            "request": {"cookies": {"df_session": "t"}, "data": {"password": "p", "email": "e"},
                        "headers": {"Cookie": "df_session=t", "Authorization": "x",
                                    "User-Agent": "ua"}},
            "user": {"id": 3, "email": "a@b.test", "ip_address": "1.2.3.4"},
        })
        assert "cookies" not in event["request"]
        assert event["request"]["headers"] == {
            "Cookie": "[scrubbed]", "Authorization": "[scrubbed]", "User-Agent": "ua"}
        assert event["request"]["data"] == {"password": "[scrubbed]", "email": "e"}
        assert event["user"] == {"id": 3}
        assert scrub({"request": {"data": "raw body"}})["request"]["data"] == "[scrubbed]"


class TestEmail:
    def test_written_to_the_outbox(self, outbox: Path):
        email_service.send("someone@example.test", "Hello", "Body text")
        [message] = _emails(outbox)
        assert (message["To"], message["Subject"]) == ("someone@example.test", "Hello")
        assert "Body text" in message.get_content()

    def test_logged_without_smtp_or_an_outbox(self, monkeypatch, caplog):
        monkeypatch.setattr(get_settings(), "smtp_host", None)
        monkeypatch.setattr(get_settings(), "email_outbox", None)
        with caplog.at_level(logging.INFO, logger="app.email"):
            email_service.send("someone@example.test", "Hello", "Body text")
        assert "no SMTP configured" in caplog.text


class TestPasswordReset:
    def test_a_reset_link_sets_a_new_password_once(self, client: TestClient,
                                                   anonymous: TestClient, outbox: Path,
                                                   db: Session):
        response = anonymous.post("/api/auth/forgot", json={"email": OWNER_EMAIL.upper()})
        assert response.status_code == 202
        [message] = _emails(outbox)
        assert message["To"] == OWNER_EMAIL
        link = re.search(r"https://dynasty\.example/reset-password\?token=(\S+)",
                         message.get_content())
        token = link.group(1)

        assert anonymous.post("/api/auth/reset", json={"token": token, "password": "short"}
                              ).status_code == 422
        assert anonymous.post("/api/auth/reset", json={"token": token,
                                                        "password": "a-new-password"}
                              ).status_code == 204
        # Signed out everywhere; the new password works; the link is spent.
        assert client.get("/api/auth/me").status_code == 401
        assert accounts.authenticate(db, OWNER_EMAIL, "a-new-password")
        again = anonymous.post("/api/auth/reset", json={"token": token, "password": "another-one"})
        assert again.status_code == 400
        assert "expired or was already used" in again.json()["detail"]

    def test_the_same_answer_for_unknown_accounts(self, anonymous: TestClient, outbox: Path):
        known = anonymous.post("/api/auth/forgot", json={"email": OWNER_EMAIL})
        unknown = anonymous.post("/api/auth/forgot", json={"email": "nobody@example.test"})
        assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())
        assert len(_emails(outbox)) == 1

    def test_links_expire_after_an_hour(self, anonymous: TestClient, db: Session):
        _, token = accounts.request_reset(db, OWNER_EMAIL)
        db.execute(update(PasswordReset).values(
            expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        response = anonymous.post("/api/auth/reset",
                                  json={"token": token, "password": "new-pass-1"})
        assert response.status_code == 400
        assert anonymous.post("/api/auth/reset", json={"token": "made-up", "password": "new-pass-1"}
                              ).status_code == 400

    def test_a_few_emails_an_hour_per_address(self, anonymous: TestClient, outbox: Path):
        for _ in range(7):
            assert anonymous.post("/api/auth/forgot", json={"email": OWNER_EMAIL}
                                  ).status_code == 202
        assert len(_emails(outbox)) == 5

    def test_deleting_the_account_removes_its_links(self, db: Session, owner):
        accounts.request_reset(db, OWNER_EMAIL)
        accounts.delete_account(db, owner, "test-owner-password")
        assert db.scalar(select(func.count(PasswordReset.id))) == 0
        assert db.scalar(select(func.count(UserSession.id))) == 0
