from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.free_agency import DEMAND, MARKET_DAYS, Bid, acceptable, demand, ranked
from app.domain.positions import ROSTER_MAX
from app.models import Franchise, FreeAgentOffer, League, Player, Season
from app.services import free_agency
from app.services.offseason import FREE_AGENT_FLOOR, advance

# ---------- pure rules ----------


def test_players_get_less_picky_each_day():
    assert list(DEMAND) == sorted(DEMAND, reverse=True)
    assert demand(1) > 1 > demand(MARKET_DAYS)
    assert demand(0) == demand(1) and demand(99) == demand(MARKET_DAYS)


def test_bids_rank_by_money_then_contenders():
    rich = Bid(offer_id=1, salary=11_000_000, price=10_000_000, team_overall=74)
    contender = Bid(offer_id=2, salary=10_500_000, price=10_000_000, team_overall=82)
    assert ranked([rich, contender])[0] is contender  # 1.05 × 1.06 beats 1.10 × 0.98
    tie_a = Bid(offer_id=3, salary=10_000_000, price=10_000_000, team_overall=76)
    tie_b = Bid(offer_id=4, salary=10_000_000, price=10_000_000, team_overall=76)
    assert ranked([tie_b, tie_a])[0] is tie_a  # earlier offer wins ties
    assert not acceptable(tie_a, day=1) and acceptable(tie_a, day=3)


# ---------- the market ----------


@pytest.fixture
def market(db: Session, league: League) -> Season:
    season = league.seasons[0]
    season.phase = "offseason"
    new_season = advance(db, season)
    db.commit()  # (to the test's savepoint) so a rejected request's rollback keeps it
    return new_season


def _view(client: TestClient, league: League) -> dict:
    return client.get(f"/api/leagues/{league.id}/free-agency").json()


def _play(client: TestClient, season: Season, until: str = "next_day") -> dict:
    return client.post(f"/api/seasons/{season.id}/free-agency", json={"until": until}).json()


def _offer(client: TestClient, player_id: int, salary: int, years: int):
    return client.post(f"/api/players/{player_id}/offer", json={"salary": salary, "years": years})


def _pending(db: Session, season: Season) -> list[FreeAgentOffer]:
    return db.scalars(select(FreeAgentOffer).where(FreeAgentOffer.season_id == season.id,
                                                   FreeAgentOffer.status == "pending")).all()


def test_rollover_opens_the_market(client: TestClient, db: Session, market: Season,
                                   franchise: Franchise, league: League):
    assert market.phase == "free_agency" and market.free_agency_day == 1
    offers = _pending(db, market)
    assert offers and all(o.team_id != franchise.team_id for o in offers)
    for offer in offers:
        player = db.get(Player, offer.player_id)
        assert player.team_id is None and player.overall >= FREE_AGENT_FLOOR
    lost = market.offseason_log["lost"]
    per_team = Counter(o.team_id for o in offers)
    assert all(per_team[t] <= len(lost.get(str(t), [])) for t in per_team)

    season = client.get("/api/franchise").json()["season"]
    assert season["phase"] == "free_agency" and season["free_agency_day"] == 1
    sim = client.post(f"/api/seasons/{market.id}/simulate", json={"until": "next_week"})
    assert sim.status_code == 409
    free_agent = db.get(Player, offers[0].player_id)
    instant = client.post(f"/api/teams/{franchise.team_id}/signings",
                          json={"player_id": free_agent.id, "years": 1})
    assert instant.status_code == 409 and "offer" in instant.json()["detail"]


def test_market_view(client: TestClient, db: Session, market: Season, league: League):
    view = _view(client, league)
    assert view["open"] is True and (view["day"], view["days"]) == (1, MARKET_DAYS)
    assert view["demand"] == DEMAND[0]
    overalls = [r["player"]["overall"] for r in view["players"]]
    assert overalls == sorted(overalls, reverse=True)
    counts = Counter(o.player_id for o in _pending(db, market))
    assert all(r["offers"] == counts[r["player"]["id"]] for r in view["players"])
    assert view["signings"] == [] and view["open_spots"] > 0


def _affordable(view: dict, premium: float) -> dict:
    """The best free agent the franchise can afford at `premium` × his asking price."""
    return next(r for r in view["players"]
                if r["asking"]["salary"] * premium <= view["cap_space"])


def test_a_premium_offer_lands_the_player(client: TestClient, db: Session, market: Season,
                                          league: League, franchise: Franchise):
    row = _affordable(_view(client, league), 1.3)
    salary = round(row["asking"]["salary"] * 1.3, -4)
    years = row["asking"]["years"]
    assert _offer(client, row["player"]["id"], salary, years).status_code == 204
    mine = next(r for r in _view(client, league)["players"]
                if r["player"]["id"] == row["player"]["id"])
    assert mine["my_offer"] == {"salary": salary, "years": years} and mine["leading"] is True

    result = _play(client, market)
    assert result["season"]["free_agency_day"] == 2
    signed = next(s for s in result["mine"] if s["player"]["id"] == row["player"]["id"])
    assert (signed["salary"], signed["years"], signed["day"]) == (salary, years, 1)
    player = db.get(Player, row["player"]["id"])
    assert player.team_id == franchise.team_id
    assert player.active_contract.start_year == market.year
    assert _view(client, league)["signings"][0]["player"]["id"] == player.id


def test_a_lowball_waits_for_the_last_day(client: TestClient, db: Session, market: Season,
                                          league: League, franchise: Franchise):
    # Below the AI's floor, so nobody else bids: he takes 85% only when the market ends.
    row = next(r for r in _view(client, league)["players"]
               if r["player"]["overall"] < FREE_AGENT_FLOOR)
    salary = max(750_000, round(row["asking"]["salary"] * 0.85, -4))
    _offer(client, row["player"]["id"], salary, row["asking"]["years"])
    _play(client, market)
    assert db.get(Player, row["player"]["id"]).team_id is None
    result = _play(client, market, "end")
    assert result["season"]["phase"] == "draft"
    signing = next(s for s in result["mine"] if s["player"]["id"] == row["player"]["id"])
    assert signing["day"] == MARKET_DAYS


def test_offer_rules(client: TestClient, db: Session, market: Season, league: League,
                     franchise: Franchise):
    view = _view(client, league)
    row = view["players"][0]
    pid = row["player"]["id"]
    rostered = db.scalars(select(Player).where(Player.team_id == franchise.team_id)).first()
    assert _offer(client, rostered.id, 1_000_000, 1).status_code == 409
    over = _offer(client, pid, min(100_000_000, view["cap_space"] + 1_000_000), 1)
    if view["cap_space"] + 1_000_000 <= 100_000_000:
        assert over.status_code == 409 and "cap" in over.json()["detail"]

    _offer(client, pid, 1_000_000, 2)
    _offer(client, pid, 2_000_000, 3)  # replaces the first
    mine = [o for o in _pending(db, market) if o.team_id == franchise.team_id]
    assert [(o.salary, o.years) for o in mine] == [(2_000_000, 3)]
    assert client.delete(f"/api/players/{pid}/offer").status_code == 204
    assert client.delete(f"/api/players/{pid}/offer").status_code == 404


def test_the_market_is_closed_outside_free_agency(client: TestClient, league: League):
    view = _view(client, league)
    assert view["open"] is False and view["day"] is None
    pid = view["players"][0]["player"]["id"]
    assert _offer(client, pid, 1_000_000, 1).status_code == 409
    season = league.seasons[0]
    assert client.post(f"/api/seasons/{season.id}/free-agency",
                       json={"until": "end"}).status_code == 409


def test_closing_opens_the_draft(
        client: TestClient, db: Session, market: Season, league: League, franchise: Franchise):
    result = _play(client, market, "end")
    assert result["season"]["phase"] == "draft"
    assert not _pending(db, market)
    log = market.offseason_log
    assert log["signed"]
    teams = client.get(f"/api/leagues/{league.id}/teams").json()
    assert all(t["roster_count"] <= ROSTER_MAX and t["cap_space"] >= 0 for t in teams)
    # AI teams don't sign back players they let go.
    departed = {e["player"]: e["team"] for e in log["departed"]}
    assert all(departed.get(e["player"]) != e["team"] for e in log["signed"])
    recap = client.get("/api/franchise/dashboard").json()["offseason"]
    assert not recap["signed"]  # the franchise made no offers
    assert client.post(f"/api/seasons/{market.id}/simulate",
                       json={"until": "next_week"}).status_code == 409


def test_market_is_deterministic(db: Session, league: League):
    def run() -> list[tuple]:
        season = league.seasons[0]
        season.phase = "offseason"
        new_season = advance(db, season)
        signings = free_agency.play_days(db, new_season, "end")
        return [(db.get(Player, s["player"]).full_name, s["team"], s["salary"], s["day"])
                for s in signings]

    savepoint = db.begin_nested()
    first = run()
    savepoint.rollback()
    db.expire_all()
    assert run() == first


def test_dashboard_during_free_agency(client: TestClient, market: Season):
    dashboard = client.get("/api/franchise/dashboard").json()
    assert any("Free agency, day 1" in a["message"] for a in dashboard["alerts"])
    assert dashboard["offseason"] is not None  # the recap so far
