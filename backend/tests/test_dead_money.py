import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import BONUS_SHARE, MIN_SALARY, dead_money, signing_bonus
from app.models import Contract, DeadMoney, Franchise, League, Player, Season
from app.services import cap
from app.services.offseason import advance

# ---------- pure rules ----------


def test_signing_bonus_is_a_share_of_the_deal():
    assert signing_bonus(10_000_000, 4) == int(BONUS_SHARE * 40_000_000)
    assert signing_bonus(MIN_SALARY, 3) == 0
    assert signing_bonus(5_000_000, 0) == 0


@pytest.mark.parametrize("end_year, cap_year, expected", [
    (2029, 2026, 12_000_000),  # four seasons left: all of it
    (2029, 2027, 9_000_000),
    (2029, 2029, 3_000_000),  # last season: one year's proration
    (2029, 2030, 0),  # deal over: nothing
])
def test_dead_money_is_the_remaining_proration(end_year, cap_year, expected):
    assert dead_money(12_000_000, 4, end_year, cap_year) == expected


# ---------- releases ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _roster(db: Session, team_id: int) -> list[Player]:
    return list(db.scalars(select(Player).where(Player.team_id == team_id)
                           .order_by(Player.overall.desc(), Player.id)))


def _with_bonus(db: Session, team_id: int, season: Season) -> Player:
    return next(p for p in _roster(db, team_id)
                if p.active_contract.signing_bonus and p.active_contract.end_year > season.year)


def test_generated_contracts_carry_bonuses(db: Session, franchise: Franchise):
    contracts = [p.active_contract for p in _roster(db, franchise.team_id)]
    assert any(c.signing_bonus for c in contracts)
    assert all(c.signing_bonus == signing_bonus(c.salary, c.years) for c in contracts)


def test_releasing_charges_the_rest_of_the_bonus(client: TestClient, db: Session,
                                                 franchise: Franchise, season: Season):
    before = client.get(f"/api/teams/{franchise.team_id}").json()
    player = _with_bonus(db, franchise.team_id, season)
    contract = player.active_contract
    expected = dead_money(contract.signing_bonus, contract.years, contract.end_year,
                          season.year)
    assert client.post(f"/api/players/{player.id}/release").status_code == 200

    charge = db.scalars(select(DeadMoney).where(DeadMoney.player_id == player.id)).one()
    assert (charge.team_id, charge.year, charge.amount, charge.reason) == \
        (franchise.team_id, season.year, expected, "released")
    after = client.get(f"/api/teams/{franchise.team_id}").json()
    assert after["dead_money"] == expected
    assert after["payroll"] == before["payroll"] - contract.salary + expected
    assert after["cap_space"] == before["cap_space"] + contract.salary - expected

    contracts = client.get(f"/api/teams/{franchise.team_id}/contracts").json()
    assert contracts["dead_money"][0] == {"player_id": player.id, "name": player.full_name,
                                          "position": player.position, "year": season.year,
                                          "amount": expected, "reason": "released"}


def test_minimum_deals_cost_nothing_to_cut(client: TestClient, db: Session, league: League,
                                           franchise: Franchise):
    cut = _roster(db, franchise.team_id)[-1]  # (room on the roster)
    client.post(f"/api/players/{cut.id}/release")
    free_agent = db.scalars(select(Player).where(Player.league_id == league.id,
                                                 Player.team_id.is_(None),
                                                 Player.id != cut.id,
                                                 Player.draft_year.is_(None))).first()
    signed = client.post(f"/api/teams/{franchise.team_id}/signings",
                         json={"player_id": free_agent.id, "years": 2,
                               "salary": MIN_SALARY}).json()
    assert signed["contract"]["signing_bonus"] == 0
    client.post(f"/api/players/{free_agent.id}/release")
    assert not db.scalars(select(DeadMoney).where(DeadMoney.player_id == free_agent.id)).all()


def test_offseason_releases_hit_next_seasons_cap(client: TestClient, db: Session,
                                                 franchise: Franchise, season: Season):
    season.phase = "offseason"
    db.commit()
    player = _with_bonus(db, franchise.team_id, season)  # (his deal runs past this season)
    salary = player.active_contract.salary
    before = client.get(f"/api/teams/{franchise.team_id}/contracts").json()
    client.post(f"/api/players/{player.id}/release")
    charge = db.scalars(select(DeadMoney).where(DeadMoney.player_id == player.id)).one()
    assert charge.year == season.year + 1 == cap.cap_year(season)
    after = client.get(f"/api/teams/{franchise.team_id}/contracts").json()
    assert after["next_year_payroll"] == before["next_year_payroll"] - salary + charge.amount


def test_dead_money_counts_against_signings(client: TestClient, db: Session, league: League,
                                            franchise: Franchise, season: Season):
    player = _with_bonus(db, franchise.team_id, season)
    client.post(f"/api/players/{player.id}/release")
    team = client.get(f"/api/teams/{franchise.team_id}").json()
    free_agent = db.scalars(select(Player).where(Player.league_id == league.id,
                                                 Player.team_id.is_(None),
                                                 Player.id != player.id)).first()
    # Exactly enough room for him only if dead money were ignored.
    league.salary_cap = team["payroll"] - team["dead_money"] + 1_000_000
    db.commit()
    response = client.post(f"/api/teams/{franchise.team_id}/signings",
                           json={"player_id": free_agent.id, "years": 1, "salary": 1_000_000})
    assert response.status_code == 409 and "cap" in response.json()["detail"]


def test_new_deals_include_bonuses(client: TestClient, db: Session, league: League,
                                   franchise: Franchise):
    roster = _roster(db, franchise.team_id)
    client.post(f"/api/players/{roster[-1].id}/release")
    free_agent = db.scalars(select(Player).where(Player.league_id == league.id,
                                                 Player.team_id.is_(None),
                                                 Player.id != roster[-1].id)
                            .order_by(Player.overall.desc())).first()
    signed = client.post(f"/api/teams/{franchise.team_id}/signings",
                         json={"player_id": free_agent.id, "years": 3}).json()
    contract = signed["contract"]
    assert contract["signing_bonus"] == signing_bonus(contract["salary"], 3) > 0


# ---------- trades and retirements ----------


def test_a_traded_player_leaves_his_bonus_behind(client: TestClient, db: Session,
                                                 league: League, franchise: Franchise,
                                                 season: Season):
    center = client.get(f"/api/leagues/{league.id}/trades").json()
    star = _with_bonus(db, franchise.team_id, season)
    old = star.active_contract
    expected = dead_money(old.signing_bonus, old.years, old.end_year, season.year)
    partner = center["partner"]["id"]
    result = client.post(f"/api/leagues/{league.id}/trades", json={
        "partner_id": partner, "send_players": [star.id],
        "receive_players": [center["theirs"]["players"][-1]["id"]]}).json()
    assert result["accepted"], result["evaluation"]

    charge = db.scalars(select(DeadMoney).where(DeadMoney.player_id == star.id)).one()
    assert (charge.team_id, charge.amount, charge.reason) == \
        (franchise.team_id, expected, "traded")
    new = star.active_contract
    assert (new.team_id, new.salary, new.signing_bonus) == (partner, old.salary, 0)
    assert (new.start_year, new.end_year) == (season.year, old.end_year)
    assert not old.is_active


def test_retiring_mid_deal_leaves_dead_money(db: Session, league: League, season: Season):
    season.phase = "offseason"
    advance(db, season)
    retired = db.scalars(select(DeadMoney).where(DeadMoney.reason == "retired")).all()
    assert retired and all(c.year == season.year + 1 for c in retired)
    for charge in retired:
        contract = db.scalars(select(Contract).where(
            Contract.player_id == charge.player_id, Contract.team_id == charge.team_id)
            .order_by(Contract.id.desc())).first()
        assert charge.amount == dead_money(contract.signing_bonus, contract.years,
                                           contract.end_year, season.year + 1)


def test_replacing_a_roster_by_import_leaves_no_dead_money(client: TestClient, db: Session,
                                                           franchise: Franchise):
    template = client.get("/api/roster-import/template.csv").content
    response = client.post(f"/api/teams/{franchise.team_id}/roster-import/commit",
                           files={"file": ("roster.csv", template)}, data={"mode": "replace"})
    assert response.status_code == 200 and response.json()["released"] == 53
    assert not db.scalars(select(DeadMoney)).all()
