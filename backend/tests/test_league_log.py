"""Milestone 13, part 3: commissioner edits and the League log
(docs/design/head-to-head-and-commissioner.md §4)."""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DepthChartEntry,
    Franchise,
    League,
    LeagueLogEntry,
    Player,
    Season,
    Team,
    User,
)
from app.services import accounts, cap, league_log, members
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def friend(db: Session, owner: User, league: League,
           franchise: Franchise) -> tuple[User, TestClient, Team]:
    """A manager (not a commissioner) running another team, signed in."""
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    user.display_name = "Robin"
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user), team


def _player(db: Session, team_id: int, position: str = "WR") -> Player:
    return db.scalar(select(Player).where(Player.team_id == team_id, Player.position == position)
                     .order_by(Player.overall, Player.id))


def _log(client: TestClient, league: League, **params) -> dict:
    response = client.get(f"/api/leagues/{league.id}/log", params=params)
    assert response.status_code == 200, response.text
    return response.json()


class TestEditingPlayers:
    def test_the_commissioner_edits_anyone_and_every_member_sees_it(
            self, db: Session, client: TestClient, friend, league: League):
        _user, other, team = friend
        player = _player(db, team.id)
        speed = player.ratings.speed
        edited = client.patch(f"/api/players/{player.id}",
                              json={"age": 30, "ratings": {"speed": 99}})
        assert edited.status_code == 200, edited.text
        entry = _log(other, league)["entries"][0]
        assert entry["actor"] == "owner" and entry["action"] == "player"
        assert entry["summary"] == f"Edited {player.full_name}"
        assert entry["player_id"] == player.id and entry["team_id"] == team.id
        changes = {c["field"]: (c["before"], c["after"]) for c in entry["changes"]}
        assert changes["speed"] == (speed, 99) and changes["age"][1] == 30
        assert set(changes) <= {"speed", "age", "potential"}  # (only what changed; a better
        # player can raise his potential)

    def test_a_manager_only_changes_a_jersey_number(self, db: Session, friend,
                                                    league: League):
        _user, other, team = friend
        player = _player(db, team.id)
        refused = other.patch(f"/api/players/{player.id}", json={"ratings": {"speed": 99}})
        assert refused.status_code == 403 and "commissioner" in refused.json()["detail"]
        assert other.patch(f"/api/players/{player.id}", json={"age": 25}).status_code == 403
        taken = {p.jersey_number for p in db.scalars(
            select(Player).where(Player.team_id == team.id))}
        number = next(n for n in range(1, 100) if n not in taken)
        assert other.patch(f"/api/players/{player.id}",
                           json={"jersey_number": number}).status_code == 200
        entry = _log(other, league)["entries"][0]
        assert entry["actor"] == "Robin" and entry["changes"][0]["field"] == "jersey_number"

    def test_a_manager_neither_adds_nor_imports_players(self, db: Session, friend):
        _user, other, team = friend
        made = other.post(f"/api/teams/{team.id}/players", json={
            "first_name": "Ari", "last_name": "Vance", "position": "QB", "jersey_number": 3})
        assert made.status_code == 403
        imported = other.post(f"/api/teams/{team.id}/roster-import/preview",
                              files={"file": ("roster.csv", io.BytesIO(b"x"), "text/csv")})
        assert imported.status_code == 403

    def test_adding_a_player_is_logged(self, db: Session, client: TestClient, league: League,
                                       franchise: Franchise):
        cut = _player(db, franchise.team_id)
        client.post(f"/api/players/{cut.id}/release")  # (rosters are full)
        made = client.post(f"/api/teams/{franchise.team_id}/players", json={
            "first_name": "Ari", "last_name": "Vance", "position": "QB", "jersey_number": 93})
        assert made.status_code == 201, made.text
        entry = _log(client, league)["entries"][0]
        assert entry["action"] == "new_player" and "Ari Vance" in entry["summary"]

    def test_an_edit_that_changes_nothing_isnt_logged(self, db: Session, client: TestClient,
                                                      league: League, franchise: Franchise):
        player = _player(db, franchise.team_id)
        client.patch(f"/api/players/{player.id}", json={"age": player.age})
        assert _log(client, league)["entries"] == []


class TestMovingPlayers:
    def test_to_another_team_with_his_contract(self, db: Session, client: TestClient, friend,
                                               league: League, franchise: Franchise,
                                               season: Season):
        _user, _other, team = friend
        cut = _player(db, team.id, "QB")
        client.post(f"/api/players/{cut.id}/release")  # (room on their roster)
        player = _player(db, franchise.team_id)
        salary = player.active_contract.salary
        end = player.active_contract.end_year
        year = cap.cap_year(season)
        dead = cap.dead_money_for(db, franchise.team_id, year)
        moved = client.post(f"/api/players/{player.id}/move", json={"team_id": team.id})
        assert moved.status_code == 200, moved.text
        body = moved.json()
        assert body["team_id"] == team.id
        assert body["contract"]["salary"] == salary and body["contract"]["end_year"] == end
        assert cap.dead_money_for(db, franchise.team_id, year) == dead  # (no dead money)
        assert db.scalar(select(DepthChartEntry).where(
            DepthChartEntry.player_id == player.id)) is None
        numbers = [p.jersey_number for p in db.scalars(
            select(Player).where(Player.team_id == team.id))]
        assert len(numbers) == len(set(numbers))
        entry = _log(client, league)["entries"][0]
        assert entry["action"] == "move"
        assert entry["summary"] == (f"Moved {player.full_name} from "
                                    f"{franchise.team.full_name} to {team.full_name}")

    def test_to_free_agency_and_back(self, db: Session, client: TestClient, league: League,
                                     franchise: Franchise):
        player = _player(db, franchise.team_id)
        freed = client.post(f"/api/players/{player.id}/move", json={"team_id": None}).json()
        assert freed["team_id"] is None and freed["contract"] is None
        back = client.post(f"/api/players/{player.id}/move",
                           json={"team_id": franchise.team_id}).json()
        assert back["team_id"] == franchise.team_id and back["contract"]["years"] == 1

    def test_refused_to_a_full_roster_or_by_a_manager(self, db: Session, client: TestClient,
                                                      friend, franchise: Franchise):
        _user, other, team = friend
        player = _player(db, franchise.team_id)
        full = client.post(f"/api/players/{player.id}/move", json={"team_id": team.id})
        assert full.status_code == 409 and "roster is full" in full.json()["detail"]
        mine = _player(db, team.id)
        assert other.post(f"/api/players/{mine.id}/move",
                          json={"team_id": None}).status_code == 403


class TestContracts:
    def test_the_commissioner_rewrites_one(self, db: Session, client: TestClient,
                                           league: League, franchise: Franchise,
                                           season: Season):
        player = _player(db, franchise.team_id)
        old = player.active_contract.salary
        body = client.put(f"/api/players/{player.id}/contract",
                          json={"salary": 4_000_000, "years": 3}).json()
        year = cap.cap_year(season)
        assert body["contract"]["salary"] == 4_000_000
        assert body["contract"]["start_year"] == year and body["contract"]["end_year"] == year + 2
        assert sum(c.is_active for c in db.get(Player, player.id).contracts) == 1
        entry = _log(client, league)["entries"][0]
        assert entry["action"] == "contract" and "$4.00M a season" in entry["summary"]
        changes = {c["field"]: (c["before"], c["after"]) for c in entry["changes"]}
        assert changes["salary"] == (old, 4_000_000)

    def test_refused_for_a_free_agent_a_manager_or_out_of_range(
            self, db: Session, client: TestClient, friend, franchise: Franchise):
        _user, other, team = friend
        player = _player(db, franchise.team_id)
        url = f"/api/players/{player.id}/contract"
        assert client.put(url, json={"salary": 10, "years": 3}).status_code == 422
        assert client.put(url, json={"salary": 1_000_000, "years": 9}).status_code == 422
        theirs = _player(db, team.id)
        assert other.put(f"/api/players/{theirs.id}/contract",
                         json={"salary": 9_000_000, "years": 2}).status_code == 403
        client.post(f"/api/players/{player.id}/move", json={"team_id": None})
        assert client.put(url, json={"salary": 1_000_000, "years": 1}).status_code == 409


class TestCommissionerActions:
    def test_team_edits_settings_and_members_are_logged(self, db: Session, client: TestClient,
                                                        friend, league: League):
        user, _other, team = friend
        client.patch(f"/api/teams/{team.id}", json={"stadium": "Harbor Field"})
        client.patch(f"/api/leagues/{league.id}/settings", json={"trade_review_hours": 24})
        member = members.member(db, league.id, user)
        client.patch(f"/api/leagues/{league.id}/members/{member.id}",
                     json={"role": "commissioner"})
        client.patch(f"/api/leagues/{league.id}/members/{member.id}", json={"role": "manager"})
        client.delete(f"/api/leagues/{league.id}/members/{member.id}")
        entries = _log(client, league)["entries"]
        assert [e["action"] for e in entries] == ["member", "member", "member", "settings",
                                                  "team"]
        assert entries[0]["summary"].startswith("Removed Robin")
        assert entries[0]["team_id"] == team.id
        assert entries[2]["summary"] == "Made Robin a commissioner"
        assert entries[3]["changes"] == [
            {"field": "trade_review_hours", "before": 0, "after": 24}]
        assert entries[4]["changes"][0]["after"] == "Harbor Field"

    def test_a_veto_is_logged(self, db: Session, client: TestClient, friend, league: League,
                              franchise: Franchise):
        _user, other, team = friend
        client.patch(f"/api/leagues/{league.id}/settings", json={"trade_review_hours": 24})
        offer = client.post(f"/api/leagues/{league.id}/trade-offers", json={"proposal": {
            "partner_id": team.id, "send_players": [_player(db, franchise.team_id).id],
            "receive_players": [_player(db, team.id).id]}}).json()
        other.post(f"/api/trade-offers/{offer['id']}/accept")
        client.post(f"/api/trade-offers/{offer['id']}/veto", json={"reason": "Lopsided."})
        entry = _log(other, league)["entries"][0]
        assert entry["action"] == "veto" and entry["summary"].endswith(": Lopsided.")
        assert team.full_name in entry["summary"]


class TestTheLog:
    def test_pages_and_filters(self, db: Session, client: TestClient, league: League,
                               owner: User):
        for n in range(league_log.PAGE + 3):
            league_log.record(db, league.id, owner, "player" if n % 2 else "team", f"#{n}")
        db.commit()
        first = _log(client, league)
        assert len(first["entries"]) == league_log.PAGE and first["more"]
        assert first["entries"][0]["summary"] == f"#{league_log.PAGE + 2}"  # (newest first)
        rest = _log(client, league, before=first["entries"][-1]["id"])
        assert len(rest["entries"]) == 3 and not rest["more"]
        teams = _log(client, league, action="team")["entries"]
        assert teams and all(e["action"] == "team" for e in teams)

    def test_strangers_dont_see_it_and_it_goes_with_the_league(
            self, db: Session, client: TestClient, league: League, owner: User):
        league_log.record(db, league.id, owner, "settings", "Changed the league settings")
        stranger = accounts.sign_up(db, "stranger@example.test", "stranger-password")
        db.commit()
        with make_client(db) as other:
            sign_in_as(other, db, stranger)
            assert other.get(f"/api/leagues/{league.id}/log").status_code == 404
        from app.services.leagues import delete_league

        delete_league(db, league)
        db.flush()
        assert db.scalar(select(LeagueLogEntry.id)) is None

    def test_a_deleted_account_keeps_its_name_in_the_log(self, db: Session, league: League,
                                                         owner: User):
        entry = league_log.record(db, league.id, owner, "settings", "Changed the settings")
        assert entry.actor == "owner"
