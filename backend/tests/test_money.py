"""Milestone 14, part 2: money (docs/design/owners-and-front-offices.md §3)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import money as rules
from app.domain import owners as owner_rules
from app.models import Franchise, Game, League, Owner, OwnerSeason, Season, Team
from app.schemas import SimulateRequest
from app.services import cap
from app.services import season as season_service
from app.services.carousel import payroll as staff_payroll
from app.services.teams import load_roster, payroll

CAP = 255_000_000


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _sim(db: Session, season: Season, until: str) -> None:
    season_service.simulate(db, season, SimulateRequest(until=until))
    db.commit()


def _url(team_id: int, path: str = "finances") -> str:
    return f"/api/teams/{team_id}/{path}"


class TestTheRules:
    def test_tickets_scale_with_the_cap_and_the_price(self):
        assert rules.ticket_price("medium", "normal", CAP) == 110
        assert rules.ticket_price("medium", "normal", CAP * 2) == 220
        assert rules.ticket_price("large", "high", CAP) == 162  # (130 × 1.25)
        assert rules.ticket_price("small", "low", CAP) == 72

    def test_fans_fill_the_stadium_and_prices_move_them(self):
        assert rules.attendance("medium", 0, "normal") == 37_400  # (55%)
        assert rules.attendance("medium", 100, "normal") == 68_000
        assert rules.attendance("medium", 100, "low") == 68_000  # (never over capacity)
        assert rules.attendance("medium", 50, "low") > rules.attendance("medium", 50, "normal")
        assert rules.attendance("medium", 50, "high") < rules.attendance("medium", 50, "normal")

    def test_merchandise_and_media(self):
        assert rules.media(CAP) == CAP
        assert rules.merchandise(CAP, "medium", 0, 0.5) == round(CAP * 0.03)
        assert rules.merchandise(CAP, "large", 5, 1.0) > rules.merchandise(CAP, "small", 0, 0.0)

    def test_profit_targets(self):
        assert rules.profit_target(CAP, "contender") == 0
        assert rules.profit_target(CAP, "rebuilding") == 20_000_000

    def test_ticket_prices_move_the_fans(self):
        season = owner_rules.Season(wins=8, losses=9, ties=0, weeks=17, ticket_price="low")
        assert dict(owner_rules.fan_change(season))["Cheap tickets"] == 3


class TestASeasonsMoney:
    def test_before_a_game_nothing_has_come_in_or_gone_out(self, client: TestClient,
                                                            franchise: Franchise):
        view = client.get(_url(franchise.team_id)).json()
        assert view["gates"] == [] and view["total_revenue"] == view["total_expenses"] == 0
        assert view["share"] == 0 and view["price_locked"] is None
        assert [p["price"] for p in view["prices"]] == ["low", "normal", "high"]
        assert view["projected_profit"] != 0  # (a full season, at today's gate)

    def test_a_regular_season_adds_up(self, db: Session, client: TestClient,
                                      franchise: Franchise, season: Season, league: League):
        _sim(db, season, "end_of_regular_season")
        team = db.get(Team, franchise.team_id)
        view = client.get(_url(team.id)).json()
        homes = db.scalars(select(Game).where(Game.season_id == season.id,
                                              Game.stage == "regular",
                                              Game.home_team_id == team.id)).all()
        assert len(view["gates"]) == len(homes) and view["share"] == 1
        for gate in view["gates"]:
            assert gate["revenue"] == gate["attendance"] * gate["price"]
            assert gate["attendance"] <= gate["capacity"] and gate["opponent"]
        revenue = {line["label"]: line["amount"] for line in view["revenue"]}
        assert revenue["Tickets"] == sum(g["revenue"] for g in view["gates"])
        assert revenue["Media"] == league.salary_cap
        expenses = {line["label"]: line["amount"] for line in view["expenses"]}
        assert expenses["Players"] == payroll(load_roster(db, team.id))
        assert expenses["Dead money"] == cap.dead_money_for(db, team.id, season.year)
        assert expenses["Staff and facilities"] == staff_payroll(db, team.id, season.year)
        assert view["profit"] == view["total_revenue"] - view["total_expenses"]
        assert view["profit"] == view["projected_profit"]  # (nothing left to play)

    def test_the_owner_keeps_the_seasons_money(self, db: Session, client: TestClient,
                                               franchise: Franchise, season: Season,
                                               league: League):
        _sim(db, season, "end_of_regular_season")
        _sim(db, season, "end_of_playoffs")
        view = client.get(_url(franchise.team_id)).json()
        row = db.scalar(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                                  OwnerSeason.team_id == franchise.team_id))
        assert row.finances["profit"] == view["profit"]
        assert view["history"] == [{"year": season.year, "revenue": view["total_revenue"],
                                    "expenses": view["total_expenses"],
                                    "profit": view["profit"]}]
        client.post(f"/api/leagues/{league.id}/rollback")
        db.expire_all()
        assert db.get(OwnerSeason, row.id).finances is None

    def test_a_profit_minded_owner_judges_the_money(self, db: Session, client: TestClient,
                                                    franchise: Franchise, season: Season):
        owner = db.scalar(select(Owner).where(Owner.team_id == franchise.team_id))
        if owner is None:
            client.get(_url(franchise.team_id, "owner"))
            owner = db.scalar(select(Owner).where(Owner.team_id == franchise.team_id))
        owner.priority = "profit"
        db.execute(OwnerSeason.__table__.delete())
        db.commit()
        card = client.get(_url(franchise.team_id, "owner")).json()
        goal = card["goals"][0]
        assert goal["kind"] == "profit" and goal["primary"]
        assert goal["status"] in ("on_track", "behind")
        _sim(db, season, "end_of_regular_season")
        _sim(db, season, "end_of_playoffs")
        review = client.get(_url(franchise.team_id, "owner")).json()["last_review"]
        money = client.get(_url(franchise.team_id)).json()
        target = db.scalar(select(OwnerSeason).where(
            OwnerSeason.team_id == franchise.team_id)).goals[0]["target"]
        assert review["results"][0]["met"] == (money["profit"] >= target)


class TestTicketPrices:
    def test_cheaper_tickets_fill_more_seats(self, db: Session, client: TestClient,
                                             franchise: Franchise, season: Season):
        changed = client.put(_url(franchise.team_id, "ticket-price"), json={"price": "low"})
        assert changed.status_code == 200 and changed.json()["ticket_price"] == "low"
        _sim(db, season, "end_of_regular_season")
        view = client.get(_url(franchise.team_id)).json()
        low = next(p["seat"] for p in view["prices"] if p["price"] == "low")
        assert all(g["price"] == low for g in view["gates"])
        card = client.get(_url(franchise.team_id, "owner")).json()
        assert dict(card["fan_parts"])["Cheap tickets"] == 3

    def test_set_between_seasons_only(self, db: Session, client: TestClient,
                                                      franchise: Franchise, season: Season):
        assert client.put(_url(franchise.team_id, "ticket-price"),
                          json={"price": "free"}).status_code == 422
        _sim(db, season, "next_week")
        refused = client.put(_url(franchise.team_id, "ticket-price"), json={"price": "high"})
        assert refused.status_code == 409 and "before the season" in refused.json()["detail"]
        assert client.get(_url(franchise.team_id)).json()["price_locked"]
