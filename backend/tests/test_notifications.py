"""Leagues with friends, part 4: notifications (docs/design/leagues-with-friends.md §6)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Franchise, League, Notification, Player, Season, Team, User
from app.schemas import TradeProposal
from app.services import accounts, free_agency, members, notifications, trade_offers, turns
from app.services.offseason import advance as run_offseason
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def friend(db: Session, owner: User, league: League,
           franchise: Franchise) -> tuple[User, TestClient, Team]:
    """A second member, running another team, signed in."""
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    user.display_name = "Robin"
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user), team


def _titles(db: Session, user: User, kind: str | None = None) -> list[str]:
    stmt = select(Notification.title).where(Notification.user_id == user.id)
    if kind:
        stmt = stmt.where(Notification.kind == kind)
    return list(db.scalars(stmt.order_by(Notification.id)))


def _backup(db: Session, team_id: int, position: str = "WR") -> Player:
    return db.scalar(select(Player).where(Player.team_id == team_id, Player.position == position)
                     .order_by(Player.overall, Player.id))


class TestTheInbox:
    def test_lists_counts_and_marks_read(self, db: Session, client: TestClient, owner: User,
                                         league: League):
        first = notifications.notify(db, owner.id, "advanced", "Week 1 is done", "Next: Week 2.",
                                     league.id, "/")
        notifications.notify(db, owner.id, "game_result", "You won", league_id=league.id)
        db.commit()
        assert client.get("/api/notifications/unread").json() == {"unread": 2}
        inbox = client.get("/api/notifications").json()
        assert [i["title"] for i in inbox["items"]] == ["You won", "Week 1 is done"]
        assert inbox["items"][1]["league"] == league.name and inbox["items"][1]["link"] == "/"
        assert client.post("/api/notifications/read", json={"ids": [first.id]}).json() == {
            "unread": 1}
        assert client.post("/api/notifications/read", json={}).json() == {"unread": 0}

    def test_each_person_sees_only_their_own(self, db: Session, client: TestClient, friend,
                                             owner: User):
        user, other, _team = friend
        notifications.notify(db, owner.id, "advanced", "Mine")
        db.commit()
        assert [i["title"] for i in other.get("/api/notifications").json()["items"]
                if i["title"] == "Mine"] == []
        mine = db.scalar(select(Notification.id).where(Notification.title == "Mine"))
        other.post("/api/notifications/read", json={"ids": [mine]})
        assert db.get(Notification, mine).read_at is None

    def test_a_key_notifies_once(self, db: Session, owner: User):
        assert notifications.notify(db, owner.id, "waiting", "Ready", key="k") is not None
        assert notifications.notify(db, owner.id, "waiting", "Ready", key="k") is None


class TestWhatNotifies:
    def test_a_friend_joining_tells_the_commissioner(self, db: Session, owner: User, friend):
        assert _titles(db, owner, "member_joined") == ["Robin joined " + friend[2].league.name]

    def test_ready_check_ins_nudge_the_last_manager_and_the_commissioner(
            self, db: Session, client: TestClient, friend, owner: User, league: League):
        user, other, _team = friend
        other.put(f"/api/leagues/{league.id}/ready", json={"ready": True})
        assert _titles(db, owner, "waiting") == ["Everyone else is ready: Week 1"]
        client.put(f"/api/leagues/{league.id}/ready", json={"ready": True})
        assert _titles(db, owner, "waiting")[-1] == "Everyone's ready: Week 1"
        assert _titles(db, user, "waiting") == []

    def test_advancing_tells_the_others_and_each_manager_their_result(
            self, db: Session, client: TestClient, friend, owner: User, league: League):
        user, _other, team = friend
        client.post(f"/api/leagues/{league.id}/advance")
        assert _titles(db, user, "advanced") == [f"{league.name}: Week 1 is done"]
        assert _titles(db, owner, "advanced") == []  # (they did it)
        result = _titles(db, user, "game_result")
        assert len(result) == 1 and result[0].startswith(f"The {team.nickname} ")
        link = db.scalar(select(Notification.link).where(Notification.user_id == user.id,
                                                         Notification.kind == "game_result"))
        assert link.startswith("/games/")

    def test_trade_offers_and_answers(self, db: Session, client: TestClient, friend,
                                      owner: User, league: League, franchise: Franchise):
        user, other, team = friend
        mine, theirs = _backup(db, franchise.team_id), _backup(db, team.id)
        offer = trade_offers.make(db, league, franchise.team_id, TradeProposal(
            partner_id=team.id, send_players=[mine.id], receive_players=[theirs.id]), "Swap?")
        db.commit()
        note = db.scalar(select(Notification).where(Notification.user_id == user.id,
                                                    Notification.kind == "trade_offer"))
        assert note.title.startswith("owner (") and note.title.endswith("offers a trade")
        assert note.body.startswith(f"You get WR {mine.full_name}")  # (their side)
        assert note.link == f"/trades?partner={franchise.team_id}"
        other.post(f"/api/trade-offers/{offer.id}/reject")
        assert _titles(db, owner, "trade_answer") == ["Robin rejected your offer"]

    def test_the_veto_window_tells_the_commissioner(self, db: Session, client: TestClient,
                                                    friend, owner: User, league: League,
                                                    franchise: Franchise):
        user, other, team = friend
        league.trade_review_hours = 24
        offer = trade_offers.make(db, league, team.id, TradeProposal(
            partner_id=franchise.team_id, send_players=[_backup(db, team.id).id],
            receive_players=[_backup(db, franchise.team_id).id]))
        db.commit()
        client.post(f"/api/trade-offers/{offer.id}/accept")
        assert _titles(db, owner, "trade_review")[0].startswith("A trade to review")
        assert "after the veto window" in _titles(db, user, "trade_answer")[0]

    def test_the_draft_clock_tells_the_manager_up(self, db: Session, friend, league: League,
                                                  season: Season):
        season.phase = "offseason"
        new = run_offseason(db, season)
        free_agency.play_days(db, new, "end")
        turns.advance(db, league)
        up = db.scalar(select(Franchise.user_id).where(
            Franchise.team_id == turns.draft.on_the_clock(db, new).team_id))
        assert _titles(db, db.get(User, up), "your_pick") == ["You're on the clock"]


class TestEmail:
    def test_off_by_default_and_chosen_by_kind(self, db: Session, client: TestClient,
                                               league: League):
        url = f"/api/leagues/{league.id}/notification-settings"
        kinds = client.get(url).json()["kinds"]
        assert {k["kind"] for k in kinds} == set(notifications.KINDS)
        assert not any(k["email"] for k in kinds)
        saved = client.put(url, json={"email": ["game_result", "trade_offer"]}).json()
        assert [k["kind"] for k in saved["kinds"] if k["email"]] == ["trade_offer", "game_result"]
        assert client.put(url, json={"email": ["spam"]}).status_code == 422

    def test_the_worker_sends_the_chosen_kinds(self, db: Session, client: TestClient,
                                               owner: User, league: League, tmp_path: Path,
                                               monkeypatch):
        monkeypatch.setattr(get_settings(), "smtp_host", None)
        monkeypatch.setattr(get_settings(), "email_outbox", str(tmp_path))
        client.put(f"/api/leagues/{league.id}/notification-settings",
                   json={"email": ["game_result"]})
        notifications.notify(db, owner.id, "game_result", "You won 24–17", "Week 1.",
                             league.id, "/games/1")
        notifications.notify(db, owner.id, "advanced", "Week 1 is done", league_id=league.id)
        db.commit()
        assert turns.tick(db, datetime.now(UTC) + timedelta(seconds=1)) == 0
        sent = [p.read_text() for p in tmp_path.glob("*.eml")]
        assert len(sent) == 1 and "Subject: You won" in sent[0] and "/games/1" in sent[0]
        assert {n.email for n in db.scalars(select(Notification))} == {"sent", None}


def test_notifications_go_with_their_league_and_account(db: Session, owner: User,
                                                        league: League, friend):
    from app.services.leagues import delete_league

    user, _other, _team = friend
    notifications.notify(db, user.id, "advanced", "Elsewhere")  # (no league)
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(Notification.id).where(Notification.league_id.is_not(None))) is None
    accounts.delete_account(db, user, "friend-password")
    db.flush()
    assert db.scalar(select(Notification.id).where(Notification.user_id == user.id)) is None
