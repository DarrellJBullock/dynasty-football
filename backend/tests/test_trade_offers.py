"""Leagues with friends, part 3: trades between managers (docs/design/leagues-with-friends.md
§5)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Franchise, League, Player, Season, Team, Trade, TradeOffer, User
from app.services import accounts, members, trade_offers, turns
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


def _best(db: Session, team_id: int) -> Player:
    return db.scalar(select(Player).where(Player.team_id == team_id)
                     .order_by(Player.overall.desc(), Player.id))


def _backup(db: Session, team_id: int, position: str = "WR") -> Player:
    return db.scalar(select(Player).where(Player.team_id == team_id, Player.position == position)
                     .order_by(Player.overall, Player.id))


def _swap(db: Session, client: TestClient, league: League, franchise: Franchise, team: Team,
          position: str = "WR"):
    """A one-for-one offer of backups (rosters are full, at 53)."""
    return _offer(client, league, team.id, [_backup(db, franchise.team_id, position).id],
                  [_backup(db, team.id, position).id])


def _offer(client: TestClient, league: League, partner: int, send: list[int],
           receive: list[int], note: str | None = None):
    return client.post(f"/api/leagues/{league.id}/trade-offers", json={
        "proposal": {"partner_id": partner, "send_players": send, "receive_players": receive},
        "note": note})


class TestOffers:
    def test_a_manager_offers_and_the_other_accepts(self, db: Session, client: TestClient,
                                                     friend, league: League,
                                                     franchise: Franchise):
        _user, other, team = friend
        mine, theirs = _backup(db, franchise.team_id), _backup(db, team.id)
        made = _offer(client, league, team.id, [mine.id], [theirs.id], "Swap receivers?")
        assert made.status_code == 201, made.text
        offer = made.json()
        assert offer["status"] == "pending" and offer["direction"] == "outgoing"
        assert offer["to_manager"] == "Robin" and offer["note"] == "Swap receivers?"
        # It waits for the other manager, who sees it in their trade center.
        assert db.get(Player, mine.id).team_id == franchise.team_id
        center = other.get(f"/api/leagues/{league.id}/trades").json()
        incoming = [o for o in center["offers"] if o["id"] == offer["id"]]
        assert incoming[0]["direction"] == "incoming"
        assert other.post(f"/api/trade-offers/{offer['id']}/accept").json()["status"] == "accepted"
        db.expire_all()
        assert db.get(Player, mine.id).team_id == team.id
        assert db.get(Player, theirs.id).team_id == franchise.team_id
        # Both see the trade, each from their own side.
        mine_history = client.get(f"/api/leagues/{league.id}/trades").json()["history"][0]
        their_history = other.get(f"/api/leagues/{league.id}/trades").json()["history"][0]
        assert mine_history["partner"]["id"] == team.id
        assert their_history["partner"]["id"] == franchise.team_id
        assert their_history["sent"][0]["id"] == theirs.id

    def test_rejecting_withdrawing_and_who_may_do_which(self, db: Session, client: TestClient,
                                                        friend, league: League,
                                                        franchise: Franchise):
        _user, other, team = friend
        offer = _swap(db, client, league, franchise, team).json()
        url = f"/api/trade-offers/{offer['id']}"
        assert client.post(f"{url}/accept").status_code == 403  # (not your offer to accept)
        assert other.post(f"{url}/withdraw").status_code == 403
        assert other.post(f"{url}/reject").json()["status"] == "rejected"
        assert other.post(f"{url}/accept").status_code == 409  # (it's rejected now)
        second = _swap(db, client, league, franchise, team, "RB").json()
        assert client.post(f"/api/trade-offers/{second['id']}/withdraw").json()[
            "status"] == "withdrawn"

    def test_a_counter_offer_goes_back_and_replaces_the_first(
            self, db: Session, client: TestClient, friend, league: League,
            franchise: Franchise):
        _user, other, team = friend
        mine, theirs = _backup(db, franchise.team_id), _backup(db, team.id)
        first = _offer(client, league, team.id, [mine.id], [theirs.id]).json()
        url = f"/api/trade-offers/{first['id']}/counter"
        wrong_way = {"proposal": {"partner_id": team.id, "send_players": []}}
        assert other.post(url, json=wrong_way).status_code == 409
        their_back = _backup(db, team.id, "RB")
        countered = other.post(url, json={"proposal": {
            "partner_id": franchise.team_id, "send_players": [their_back.id],
            "receive_players": [mine.id]}, "note": "Take my running back instead."})
        assert countered.status_code == 201, countered.text
        reply = countered.json()
        assert reply["parent_id"] == first["id"] and reply["direction"] == "outgoing"
        assert db.get(TradeOffer, first["id"]).status == "countered"
        assert client.post(f"/api/trade-offers/{reply['id']}/accept").json()[
            "status"] == "accepted"
        db.expire_all()
        assert db.get(Player, mine.id).team_id == team.id

    def test_ai_teams_answer_at_once_and_managers_by_offer(self, db: Session,
                                                            client: TestClient, friend,
                                                            league: League,
                                                            franchise: Franchise):
        _user, _other, team = friend
        ai = db.scalar(select(Team).where(Team.league_id == league.id,
                                          Team.id.not_in([franchise.team_id, team.id])))
        mine = _backup(db, franchise.team_id)
        assert _offer(client, league, ai.id, [mine.id], [_backup(db, ai.id).id]).status_code == 409
        proposal = {"partner_id": team.id, "send_players": [mine.id],
                    "receive_players": [_backup(db, team.id).id]}
        refused = client.post(f"/api/leagues/{league.id}/trades", json=proposal)
        assert refused.status_code == 409 and "send them an offer" in refused.json()["detail"]
        evaluation = client.post(f"/api/leagues/{league.id}/trades/evaluate",
                                 json=proposal).json()
        assert evaluation["acceptable"] and "decides" in evaluation["message"]
        center = client.get(f"/api/leagues/{league.id}/trades?partner_id={team.id}").json()
        assert center["partner"]["id"] == team.id and center["partner_manager"] == "Robin"
        assert center["managed"] == [team.id]

    def test_an_offer_the_rules_won_t_allow_isn_t_sent(self, db: Session, client: TestClient,
                                                       friend, league: League,
                                                       franchise: Franchise, season: Season):
        _user, _other, team = friend
        season.phase = "playoffs"
        db.commit()
        made = _swap(db, client, league, franchise, team)
        assert made.status_code == 409 and "closed during the playoffs" in made.json()["detail"]


class TestSettling:
    def test_offers_expire(self, db: Session, client: TestClient, friend, league: League,
                           franchise: Franchise):
        _user, other, team = friend
        offer = _swap(db, client, league, franchise, team).json()
        trade_offers.settle(db, league, datetime.now(UTC) + timedelta(days=4))
        assert db.get(TradeOffer, offer["id"]).status == "expired"
        assert other.post(f"/api/trade-offers/{offer['id']}/accept").status_code == 409

    def test_an_offer_whose_player_moved_is_no_longer_valid(self, db: Session,
                                                            client: TestClient, friend,
                                                            league: League,
                                                            franchise: Franchise):
        _user, other, team = friend
        player = _backup(db, franchise.team_id)
        offer = _swap(db, client, league, franchise, team).json()
        assert client.post(f"/api/players/{player.id}/release").status_code == 200
        response = other.post(f"/api/trade-offers/{offer['id']}/accept")
        assert response.status_code == 409 and "invalid" in response.json()["detail"]

    def test_a_completed_trade_voids_other_offers_with_its_players(
            self, db: Session, client: TestClient, friend, league: League,
            franchise: Franchise):
        _user, other, team = friend
        player = _backup(db, franchise.team_id)
        first = _swap(db, client, league, franchise, team).json()
        second = _offer(client, league, team.id, [player.id, _best(db, franchise.team_id).id],
                        [_backup(db, team.id, "RB").id, _backup(db, team.id, "TE").id]).json()
        other.post(f"/api/trade-offers/{first['id']}/accept")
        assert db.get(TradeOffer, second["id"]).status == "invalid"

    def test_a_manager_leaving_voids_their_offers(self, db: Session, client: TestClient,
                                                  friend, league: League, franchise: Franchise):
        user, _other, team = friend
        offer = _swap(db, client, league, franchise, team).json()
        members.remove(db, league, user, members.member(db, league.id, user).id)
        trade_offers.settle(db, league)
        assert db.get(TradeOffer, offer["id"]).status == "invalid"


class TestTheVetoWindow:
    def _accepted(self, db, client, other, league, franchise, team, position="WR"):
        client.patch(f"/api/leagues/{league.id}/settings", json={"trade_review_hours": 24})
        player = _backup(db, franchise.team_id, position)
        offer = _swap(db, client, league, franchise, team, position).json()
        reviewed = other.post(f"/api/trade-offers/{offer['id']}/accept").json()
        assert reviewed["status"] == "review" and reviewed["review_ends_at"]
        assert db.get(Player, player.id).team_id == franchise.team_id  # (not yet)
        return offer["id"], player

    def test_the_commissioner_can_veto_during_it(self, db: Session, client: TestClient,
                                                 friend, league: League, franchise: Franchise):
        _user, other, team = friend
        offer_id, player = self._accepted(db, client, other, league, franchise, team)
        center = client.get(f"/api/leagues/{league.id}/trades").json()
        assert [o["status"] for o in center["offers"] if o["id"] == offer_id] == ["review"]
        assert other.post(f"/api/trade-offers/{offer_id}/veto", json={}).status_code == 403
        vetoed = client.post(f"/api/trade-offers/{offer_id}/veto",
                             json={"reason": "Too lopsided."}).json()
        assert vetoed["status"] == "vetoed" and vetoed["reason"] == "Too lopsided."
        db.expire_all()
        assert db.get(Player, player.id).team_id == franchise.team_id

    def test_the_trade_goes_through_when_it_ends_or_when_approved(
            self, db: Session, client: TestClient, friend, league: League,
            franchise: Franchise):
        _user, other, team = friend
        offer_id, player = self._accepted(db, client, other, league, franchise, team)
        trade_offers.settle(db, league, datetime.now(UTC) + timedelta(hours=23))
        assert db.get(TradeOffer, offer_id).status == "review"
        assert turns.tick(db, datetime.now(UTC) + timedelta(hours=25)) >= 0
        db.expire_all()
        assert db.get(TradeOffer, offer_id).status == "accepted"
        assert db.get(Player, player.id).team_id == team.id
        second, other_player = self._accepted(db, client, other, league, franchise, team,
                                              "RB")
        assert client.post(f"/api/trade-offers/{second}/approve").json()["status"] == "accepted"
        db.expire_all()
        assert db.get(Player, other_player.id).team_id == team.id

    def test_settings_offer_none_24_or_48_hours(self, client: TestClient, league: League):
        url = f"/api/leagues/{league.id}/settings"
        assert client.patch(url, json={"trade_review_hours": 12}).status_code == 422
        assert client.patch(url, json={"trade_review_hours": 48}).json()[
            "trade_review_hours"] == 48


def test_offers_go_with_their_league(db: Session, client: TestClient, friend, league: League,
                                     franchise: Franchise):
    from app.services.leagues import delete_league

    _user, other, team = friend
    offer = _swap(db, client, league, franchise, team).json()
    other.post(f"/api/trade-offers/{offer['id']}/accept")
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(TradeOffer.id)) is None
    assert db.scalar(select(Trade.id)) is None
