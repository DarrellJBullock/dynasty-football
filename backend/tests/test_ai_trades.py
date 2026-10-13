"""Milestone 14, part 5: AI trades (docs/design/owners-and-front-offices.md §5)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parity
from app.models import (
    DraftPick,
    Franchise,
    League,
    Notification,
    Player,
    Season,
    Team,
    Trade,
    TradeOffer,
)
from app.schemas import SimulateRequest
from app.services import ai_trades
from app.services import season as season_service
from app.services.members import human_team_ids


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def certain(monkeypatch):
    """Every chance taken."""
    monkeypatch.setattr(ai_trades, "OFFER_CHANCE", 1.0)
    monkeypatch.setattr(ai_trades, "DEADLINE_DEAL_CHANCE", 1.0)


def _directions(db: Session, league: League, going: str) -> list[Team]:
    humans = human_team_ids(db, league.id)
    ai = sorted((t for t in league.teams if t.id not in humans), key=lambda t: t.id)
    for team in ai:
        team.direction, team.direction_reasons = going, ["(set by the test)"]
    db.flush()
    return ai


def _star(db: Session, team: Team, age: int = 31, overall: int = 92) -> Player:
    """Make one of the team's wide receivers a star (an upgrade for anyone)."""
    player = db.scalar(select(Player).where(Player.team_id == team.id, Player.position == "WR")
                       .order_by(Player.overall))
    player.age, player.overall = age, overall
    db.flush()
    return player


class TestOffersToManagers:
    def test_a_contender_offers_picks_for_a_player_it_needs(
            self, db: Session, certain, league: League, franchise: Franchise, season: Season):
        _directions(db, league, "contend")
        star = _star(db, db.get(Team, franchise.team_id), age=27)
        made = ai_trades.offer_managers(db, league, season, 1)
        assert len(made) == 1
        offer = made[0]
        assert offer.to_team_id == franchise.team_id and offer.status == "pending"
        assert offer.receive == [{"kind": "player", "id": star.id}]
        assert offer.send and {i["kind"] for i in offer.send} <= {"pick", "player"}
        assert "contending and want WR" in offer.note
        assert db.scalar(select(Notification.title).where(
            Notification.kind == "trade_offer")).endswith("offer a trade")
        # One open AI offer at a time.
        assert ai_trades.offer_managers(db, league, season, 2) == []

    def test_a_rebuilder_offers_a_veteran_for_picks(self, db: Session, certain, league: League,
                                                    franchise: Franchise, season: Season):
        ai = _directions(db, league, "middle")  # (the middle doesn't shop...)
        ai[0].direction = "rebuild"  # (...so the offer is this rebuilder's)
        best = max(p.overall for p in db.scalars(select(Player).where(
            Player.team_id == franchise.team_id, Player.position == "WR")))
        veteran = _star(db, ai[0], overall=best + 6)  # (just better than the member's)
        offer = ai_trades.offer_managers(db, league, season, 1)[0]
        assert offer.from_team_id == ai[0].id and offer.send == [
            {"kind": "player", "id": veteran.id}]
        assert offer.receive and {i["kind"] for i in offer.receive} <= {"pick", "player"}
        assert "rebuilding" in offer.note

    def test_accepting_needs_no_veto_window(self, db: Session, client: TestClient, certain,
                                           league: League, franchise: Franchise,
                                           season: Season):
        league.trade_review_hours = 24
        _directions(db, league, "contend")
        star = _star(db, db.get(Team, franchise.team_id), age=27)
        offer = ai_trades.offer_managers(db, league, season, 1)[0]
        db.commit()
        accepted = client.post(f"/api/trade-offers/{offer.id}/accept")
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "accepted"
        db.expire_all()
        assert db.get(Player, star.id).team_id == offer.from_team_id
        trade = db.get(Trade, db.get(TradeOffer, offer.id).trade_id)
        assert trade.team_id == offer.from_team_id  # (the AI proposed it)

    def test_a_counter_is_answered_at_once(self, db: Session, client: TestClient, certain,
                                           league: League, franchise: Franchise,
                                           season: Season):
        _directions(db, league, "contend")
        star = _star(db, db.get(Team, franchise.team_id), age=27)
        offer = ai_trades.offer_managers(db, league, season, 1)[0]
        db.commit()
        # Ask for every pick they have, as well: too much.
        picks = db.scalars(select(DraftPick.id).where(DraftPick.team_id == offer.from_team_id,
                                                      DraftPick.player_id.is_(None))).all()
        body = {"proposal": {"partner_id": offer.from_team_id, "send_players": [star.id],
                             "receive_picks": list(picks)}}
        answered = client.post(f"/api/trade-offers/{offer.id}/counter", json=body)
        assert answered.status_code == 201, answered.text
        assert answered.json()["status"] == "countered"
        assert answered.json()["reason"].startswith("They turned your counter-offer down")
        db.expire_all()
        assert db.get(Player, star.id).team_id == franchise.team_id

    def test_not_once_the_deadline_has_passed(self, db: Session, certain, league: League,
                                              season: Season, franchise: Franchise):
        _directions(db, league, "contend")
        _star(db, db.get(Team, franchise.team_id), age=27)
        season.phase, season.current_week = "regular_season", 12
        assert ai_trades.offer_managers(db, league, season, 11) == []

    def test_after_a_simulated_week(self, db: Session, certain, league: League,
                                    franchise: Franchise, season: Season):
        _directions(db, league, "contend")
        _star(db, db.get(Team, franchise.team_id), age=27)
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        assert db.scalar(select(TradeOffer).where(TradeOffer.to_team_id == franchise.team_id))


class TestDeadlineDeals:
    def test_a_contender_buys_a_veteran_from_a_rebuilder(self, db: Session, client: TestClient,
                                                         certain, league: League,
                                                         franchise: Franchise, season: Season):
        ai = _directions(db, league, "contend")
        seller = ai[0]
        seller.direction = "rebuild"
        veteran = _star(db, seller)
        season.phase, season.current_week = "regular_season", 9
        made = ai_trades.deadline_deals(db, league, season, 9)
        assert len(made) == 1 and made[0].partner_id == seller.id
        db.commit()
        bought = made[0].received
        assert len(bought) == 1 and bought[0]["kind"] == "player"
        moved = db.get(Player, bought[0]["id"])
        assert moved.team_id == made[0].team_id and moved.age >= ai_trades.VETERAN_AGE
        assert veteran.overall >= ai_trades.VETERAN_OVERALL  # (one of the seller's veterans)
        listed = client.get(f"/api/leagues/{league.id}/transactions").json()
        assert listed[0]["between"] == "ai" and listed[0]["partner"]["id"] == seller.id

    def test_only_in_the_weeks_before_the_deadline(self, db: Session, certain, league: League,
                                                   season: Season):
        ai = _directions(db, league, "contend")
        ai[0].direction = "rebuild"
        _star(db, ai[0])
        season.phase = "regular_season"
        assert ai_trades.deadline_deals(db, league, season, 4) == []
        assert ai_trades.deadline_deals(db, league, season, 11) == []


def test_transactions_say_who_traded(db: Session, client: TestClient, league: League,
                                     franchise: Franchise, season: Season):
    center = client.get(f"/api/leagues/{league.id}/trades").json()
    proposal = {"partner_id": center["partner"]["id"],
                "send_players": [center["mine"]["players"][0]["id"]],
                "receive_players": [center["theirs"]["players"][-1]["id"]]}
    assert client.post(f"/api/leagues/{league.id}/trades", json=proposal).json()["accepted"]
    listed = client.get(f"/api/leagues/{league.id}/transactions").json()
    assert listed[0]["between"] == "manager_and_ai" and listed[0]["year"] == season.year
    assert client.get(f"/api/leagues/{league.id}/transactions",
                      params={"year": season.year - 5}).json() == []


class TestParity:
    def _season(self, year: int, pcts: list[float], champion: int) -> parity.SeasonResult:
        return parity.SeasonResult(year, dict(enumerate(pcts)), champion)

    def test_a_competitive_league(self):
        base = [0.8, 0.6, 0.5, 0.4, 0.2]
        seasons = [self._season(2026 + i, base[i % 5:] + base[:i % 5], i) for i in range(6)]
        summary = parity.summarize(seasons)
        assert summary.problems == [] and summary.champions == 6

    def test_a_league_of_dynasties(self):
        seasons = [self._season(2026 + i, [1.0, 0.95, 0.05, 0.0], 0) for i in range(9)]
        summary = parity.summarize(seasons)
        assert summary.champions == 1 and summary.best_streak == 9
        assert any("different champions" in p for p in summary.problems)
        assert any("records spread" in p for p in summary.problems)
        assert any("best record 9 seasons" in p for p in summary.problems)
