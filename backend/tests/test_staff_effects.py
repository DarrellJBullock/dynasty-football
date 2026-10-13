"""Milestone 12, part 3: what staff do (docs/design/staff-and-legacy.md §3)."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import development
from app.domain import staff as rules
from app.domain.draft import SCOUTING_REPORTS
from app.models import Franchise, League, Player, StaffMember
from app.services import draft, injuries, staff
from app.sim.injuries import SEASON_ENDING

C = rules.Coach


# ---------- the rules ----------

def test_an_average_staff_changes_nothing():
    assert rules.growth_lift("QB", C(50), C(50)) == 0
    assert rules.decline_cut(C(50), C(50)) == 0
    assert rules.development_factors("QB", None, None) == (1.0, 1.0)
    assert rules.scout_scale(C(50)) == 1.0 and rules.scouting_reports(25, C(50)) == 25
    assert rules.layoff(6, C(50), SEASON_ENDING) == 6


def test_better_coaches_grow_young_players_faster_and_slow_decline():
    assert rules.growth_lift("QB", C(90), None) == pytest.approx(0.25)
    assert rules.growth_lift("QB", C(90, "QB"), None) == pytest.approx(0.35)  # (his specialty)
    assert rules.growth_lift("WR", C(90, "QB"), None) == pytest.approx(0.25)
    assert rules.growth_lift("QB", None, C(90)) == pytest.approx(0.10)  # (a head coach: 40%)
    assert rules.growth_lift("QB", C(40), None) < 0  # (a poor one holds them back)
    assert rules.decline_cut(C(90), None) == pytest.approx(0.20)
    growth, decline = rules.development_factors("DE", C(99, "DL"), C(99, "defense"))
    assert growth <= rules.FACTOR_MAX and decline >= rules.FACTOR_MIN


def test_who_coaches_whom():
    assert rules.coordinator_role("QB") == "offensive_coordinator"
    assert rules.coordinator_role("OG") == "offensive_coordinator"
    assert rules.coordinator_role("SS") == "defensive_coordinator"
    assert rules.coordinator_role("K") is None  # (kickers: the head coach only)


def test_development_scales_without_new_draws():
    def run(growth: float, decline: float, age: int) -> tuple[float, float]:
        rng = random.Random(7)
        change = development.overall_change(rng, "QB", age, 60, 85, "normal", growth, decline)
        return change, rng.random()  # (the next draw: the same either way)

    plain, after = run(1.0, 1.0, 23)
    boosted, after_boosted = run(1.25, 1.0, 23)
    assert boosted == pytest.approx(plain * 1.25) and after == after_boosted
    old, _ = run(1.0, 1.0, 34)
    slowed, _ = run(1.0, 0.8, 34)
    assert slowed == pytest.approx(old * 0.8) and slowed > old  # (a smaller loss)


def test_scouts_and_trainers():
    assert rules.scout_scale(C(90)) == pytest.approx(0.5)
    assert rules.scout_scale(C(40)) > 1
    assert rules.scouting_reports(25, C(90)) == 33 and rules.scouting_reports(25, C(40)) == 23
    assert rules.layoff(10, C(90), SEASON_ENDING) == 7
    assert rules.layoff(1, C(99), SEASON_ENDING) == 1  # (a week is a week)
    assert rules.layoff(SEASON_ENDING, C(99), SEASON_ENDING) == SEASON_ENDING
    assert rules.layoff(4, C(40), SEASON_ENDING) == 4  # (round(4 × 1.075))


def test_each_role_s_effect_in_a_line():
    assert rules.effect_text("offensive_coordinator", 90, "QB") == (
        "Young offensive players grow 25% faster (35% at QB); veterans decline 20% slower.")
    assert rules.effect_text("scout", 90, None) == (
        "Draft projections 50% closer; +8 scouting reports a class.")
    assert rules.effect_text("trainer", 90, None) == "Injured players come back 30% sooner."
    assert "slower" in rules.effect_text("head_coach", 40, "offense")


# ---------- in a league ----------

def _set(db: Session, team_id: int, role: str, rating: int, specialty: str | None = None):
    member = db.scalar(select(StaffMember).where(StaffMember.team_id == team_id,
                                                 StaffMember.role == role))
    member.rating, member.specialty = rating, specialty
    db.flush()
    return member


def test_the_offseason_uses_each_player_s_coaches(db: Session, league: League,
                                                  franchise: Franchise):
    crew = staff.by_team(db, league)
    _set(db, franchise.team_id, "offensive_coordinator", 90, "QB")
    _set(db, franchise.team_id, "head_coach", 50)
    qb = db.scalar(select(Player).where(Player.team_id == franchise.team_id,
                                        Player.position == "QB"))
    assert staff.development_factors(crew, qb) == pytest.approx((1.35, 0.8))
    free_agent = db.scalar(select(Player).where(Player.team_id.is_(None),
                                                Player.retired_year.is_(None)))
    assert staff.development_factors(crew, free_agent) == (1.0, 1.0)


def test_the_team_s_scout_sharpens_its_draft_board(db: Session, client: TestClient,
                                                  league: League, franchise: Franchise):
    staff.ensure_staff(db, league)
    _set(db, franchise.team_id, "scout", 90)
    db.commit()
    assert draft.scouting(db, league.id, franchise.team_id) == (pytest.approx(0.5),
                                                               SCOUTING_REPORTS + 8)
    view = client.get(f"/api/leagues/{league.id}/draft").json()
    assert view["scouting_left"] == SCOUTING_REPORTS + 8
    prospects = {p.id: p for p in db.scalars(select(Player).where(Player.is_prospect))}
    for row in view["prospects"][:20]:
        truth = prospects[row["id"]]
        plain = draft.projection(league.id, truth)[0]
        assert abs(row["projected"] - truth.overall) <= abs(plain - truth.overall)


def test_the_team_s_trainer_shortens_layoffs(db: Session, league: League,
                                             franchise: Franchise):
    staff.ensure_staff(db, league)
    _set(db, franchise.team_id, "trainer", 90)
    hurt = db.scalar(select(Player).where(Player.team_id == franchise.team_id))
    injuries.after_week(db, league.id, [{"player": hurt.id, "injury": "Sprained ankle",
                                         "weeks": 10}])
    assert hurt.injury_weeks == 7 and hurt.injury_status == "injured_reserve"


def test_the_player_page_explains_his_coaching(db: Session, client: TestClient,
                                               league: League, franchise: Franchise):
    staff.ensure_staff(db, league)
    _set(db, franchise.team_id, "offensive_coordinator", 90, "QB")
    _set(db, franchise.team_id, "head_coach", 50)
    _set(db, franchise.team_id, "trainer", 70)
    young = db.scalar(select(Player).where(Player.team_id == franchise.team_id,
                                           Player.position == "QB").order_by(Player.age))
    young.age = 22
    db.commit()
    body = client.get(f"/api/players/{young.id}/coaching").json()
    assert body["phase"] == "growing"
    assert body["development"] == ("With these coaches he grows 35% faster this offseason "
                                   "than he would on his own.")
    assert [i["role"] for i in body["items"]] == ["offensive_coordinator", "head_coach",
                                                  "trainer"]
    assert body["injuries"] == "Injured players come back 15% sooner."
    young.age = 33
    db.commit()
    assert "declines 20% slower" in client.get(
        f"/api/players/{young.id}/coaching").json()["development"]
    free_agent = db.scalar(select(Player).where(Player.team_id.is_(None),
                                                Player.retired_year.is_(None),
                                                Player.is_prospect.is_(False)))
    assert client.get(f"/api/players/{free_agent.id}/coaching").json()["items"] == []


def test_the_staff_page_says_what_each_does(client: TestClient, db: Session, league: League,
                                            franchise: Franchise):
    staff.ensure_staff(db, league)
    _set(db, franchise.team_id, "trainer", 90)
    db.commit()
    members = client.get(f"/api/teams/{franchise.team_id}/staff").json()["members"]
    trainer = next(m for m in members if m["role"] == "trainer")
    assert trainer["effect"] == "Injured players come back 30% sooner."
