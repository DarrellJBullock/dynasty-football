import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import (
    MIN_SALARY,
    market_salary,
    preferred_years,
    required_salary,
)
from app.domain.positions import Position
from app.models import Franchise, League, Player, Season
from tests.conftest import rollover

# ---------- pure rules ----------


@pytest.mark.parametrize("age, years", [(23, 4), (26, 4), (28, 3), (31, 2), (34, 1)])
def test_preferred_years(age, years):
    assert preferred_years(age) == years


def test_required_salary_charges_for_unwanted_lengths():
    at_preference = required_salary(Position.WR, 84, 27, 3)
    assert at_preference == market_salary(Position.WR, 84)
    assert required_salary(Position.WR, 84, 27, 5) > required_salary(Position.WR, 84, 27, 4) \
        > at_preference
    assert required_salary(Position.WR, 84, 27, 1) > at_preference
    assert required_salary(Position.K, 40, 35, 1) == MIN_SALARY


# ---------- re-signing ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _offseason(db: Session, season: Season) -> None:
    """Skip to the offseason. Committed (to the test's savepoint) so a rejected request's
    rollback doesn't undo it."""
    season.phase = "offseason"
    db.commit()


def _expiring(client: TestClient, franchise: Franchise) -> list[dict]:
    return client.get(f"/api/teams/{franchise.team_id}/contracts").json()["expiring"]


def _offer(client: TestClient, player_id: int, salary: int, years: int):
    return client.post(f"/api/players/{player_id}/re-sign",
                       json={"salary": salary, "years": years})


def test_contracts_overview(client: TestClient, franchise: Franchise, season: Season):
    body = client.get(f"/api/teams/{franchise.team_id}/contracts").json()
    team = client.get(f"/api/teams/{franchise.team_id}").json()
    assert body["window_open"] is False
    assert body["payroll"] == team["payroll"]
    assert body["next_year_payroll"] < body["payroll"]  # expiring deals drop off
    salaries = [p["contract"]["salary"] for p in body["players"]]
    assert salaries == sorted(salaries, reverse=True) and len(salaries) == team["roster_count"]
    assert body["expiring"]
    for row in body["expiring"]:
        assert row["player"]["contract"]["end_year"] == season.year
        assert row["asking"]["years"] == preferred_years(row["player"]["age"])
        assert row["re_signed"] is None


def test_re_signing_waits_for_the_offseason(client: TestClient, franchise: Franchise):
    player = _expiring(client, franchise)[0]
    response = _offer(client, player["player"]["id"], 50_000_000, 3)
    assert response.status_code == 409
    assert "season is over" in response.json()["detail"]


def test_negotiation(client: TestClient, db: Session, franchise: Franchise, season: Season):
    _offseason(db, season)
    row = _expiring(client, franchise)[0]
    player_id, ask = row["player"]["id"], row["asking"]

    lowball = _offer(client, player_id, ask["salary"] // 2, ask["years"]).json()
    assert lowball["accepted"] is False
    assert lowball["counter"] == ask
    assert "wants at least" in lowball["message"]

    # Off his preferred length he wants more.
    longer = _offer(client, player_id, ask["salary"], 5).json()
    if ask["years"] != 5:
        assert longer["accepted"] is False and longer["counter"]["salary"] > ask["salary"]

    deal = _offer(client, player_id, ask["salary"], ask["years"]).json()
    assert deal["accepted"] is True and deal["counter"] is None
    contract = deal["player"]["contract"]
    assert contract["start_year"] == season.year + 1
    assert (contract["years"], contract["salary"]) == (ask["years"], ask["salary"])
    player = db.get(Player, player_id)
    assert sum(c.is_active for c in player.contracts) == 1

    row = next(r for r in _expiring(client, franchise) if r["player"]["id"] == player_id)
    assert row["re_signed"]["salary"] == ask["salary"]
    again = _offer(client, player_id, ask["salary"], ask["years"])
    assert again.status_code == 409 and "already re-signed" in again.json()["detail"]


def test_only_expiring_players_and_only_under_the_cap(
        client: TestClient, db: Session, franchise: Franchise, season: Season, league: League):
    _offseason(db, season)
    body = client.get(f"/api/teams/{franchise.team_id}/contracts").json()
    expiring_ids = {r["player"]["id"] for r in body["expiring"]}
    locked = next(p for p in body["players"] if p["id"] not in expiring_ids)
    response = _offer(client, locked["id"], 10_000_000, 2)
    assert response.status_code == 409 and "final year" in response.json()["detail"]

    row = body["expiring"][0]
    league.salary_cap = body["next_year_payroll"] + row["asking"]["salary"] - 1
    response = _offer(client, row["player"]["id"], row["asking"]["salary"],
                      row["asking"]["years"])
    assert response.status_code == 409 and "over the cap" in response.json()["detail"]


def test_rollover_keeps_re_signed_players_and_lets_the_rest_go(
        client: TestClient, db: Session, franchise: Franchise, season: Season):
    _offseason(db, season)
    rows = _expiring(client, franchise)
    keep, let_go = rows[0], rows[1:]
    _offer(client, keep["player"]["id"], keep["asking"]["salary"], keep["asking"]["years"])

    new_season = rollover(db, season)
    kept = db.get(Player, keep["player"]["id"])
    if kept.retired_year is None:
        assert kept.team_id == franchise.team_id
        assert kept.active_contract.end_year >= new_season.year
    for row in let_go:
        assert db.get(Player, row["player"]["id"]).team_id != franchise.team_id
    departed = {e["player"] for e in new_season.offseason_log["departed"]
                if e["team"] == franchise.team_id}
    retired = {e["player"] for e in new_season.offseason_log["retired"]}
    assert {r["player"]["id"] for r in let_go} == departed | (
        {r["player"]["id"] for r in let_go} & retired)
    # AI teams still re-sign on their own.
    assert any(e["team"] != franchise.team_id for e in new_season.offseason_log["re_signed"])


def test_offseason_signings_start_next_season(client: TestClient, db: Session,
                                              franchise: Franchise, season: Season,
                                              league: League):
    _offseason(db, season)
    roster = client.get(f"/api/teams/{franchise.team_id}/roster").json()
    client.post(f"/api/players/{roster[-1]['id']}/release")
    free_agent = client.get(f"/api/leagues/{league.id}/free-agents").json()[0]
    signed = client.post(f"/api/teams/{franchise.team_id}/signings",
                         json={"player_id": free_agent["id"], "years": 1}).json()
    assert signed["contract"]["start_year"] == season.year + 1

    rollover(db, season)
    player = db.get(Player, free_agent["id"])
    assert player.team_id == franchise.team_id  # a one-year deal didn't expire at once


def test_dashboard_reminds_to_re_sign(client: TestClient, db: Session, season: Season):
    _offseason(db, season)
    alerts = client.get("/api/franchise/dashboard").json()["alerts"]
    assert any("Contracts page" in a["message"] for a in alerts)


def test_contract_404s(client: TestClient):
    assert client.get("/api/teams/999999/contracts").status_code == 404
    assert _offer(client, 999999, 1_000_000, 1).status_code == 404


def test_free_agents_cannot_negotiate(client: TestClient, db: Session, season: Season,
                                      league: League):
    _offseason(db, season)
    free_agent = db.scalars(select(Player).where(Player.league_id == league.id,
                                                 Player.team_id.is_(None))).first()
    assert _offer(client, free_agent.id, 1_000_000, 1).status_code == 409
