"""Milestone 12, part 5: facilities (docs/design/staff-and-legacy.md §3)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.models import Facility, Franchise, League, Notification, Player, Season, Team, User
from app.services import carousel, draft, facilities, injuries, staff
from app.sim.injuries import SEASON_ENDING

C = rules.Coach


# ---------- the rules ----------

def test_level_one_adds_nothing_and_each_level_adds_more():
    assert rules.growth_lift("QB", None, None, 1) == 0
    assert rules.growth_lift("QB", None, None, 5) == pytest.approx(0.16)
    assert rules.decline_cut(None, None, 3) == pytest.approx(0.06)
    assert rules.layoff(10, None, SEASON_ENDING, 5) == 8  # (20% sooner)
    assert rules.layoff(10, C(90), SEASON_ENDING, 5) == 6  # (with a 90 trainer: 50%, at the floor)
    assert rules.scout_scale(None, 5) == pytest.approx(0.76)
    assert rules.scouting_reports(25, None, 4) == 28


def test_upkeep_and_what_each_level_does():
    assert rules.upkeep(1) == 0 and rules.upkeep(4) == 900_000
    assert rules.facility_effect("medical", 1) == "Level 1: adds nothing yet."
    assert rules.facility_effect("medical", 3) == "Injured players come back 10% sooner."
    assert rules.facility_effect("scouting", 2) == (
        "Draft projections 6% closer; +1 scouting reports a class.")


def test_an_ai_team_builds_its_weakest_it_can_afford():
    assert rules.ai_upgrade({"training": 1, "medical": 1, "scouting": 1}, 10_000_000) == "training"
    assert rules.ai_upgrade({"training": 3, "medical": 2, "scouting": 2}, 10_000_000) == "medical"
    assert rules.ai_upgrade({"training": 1}, 500_000) is None
    assert rules.ai_upgrade({k: 5 for k in rules.FACILITIES}, 99_000_000) is None


# ---------- in a league ----------

@pytest.fixture
def season(db: Session, league: League) -> Season:
    staff.ensure_staff(db, league)
    facilities.ensure_facilities(db, league)
    db.commit()
    return league.seasons[0]


def _facility(db: Session, team_id: int, kind: str) -> Facility:
    return db.scalar(select(Facility).where(Facility.team_id == team_id, Facility.kind == kind))


def test_an_upgrade_is_paid_now_and_arrives_next_season(db: Session, client: TestClient,
                                                        season: Season, franchise: Franchise,
                                                        league: League):
    team = db.get(Team, franchise.team_id)
    before = carousel.budget(db, team, season.year).payroll
    url = f"/api/teams/{franchise.team_id}/facilities/training/upgrade"
    body = client.post(url)
    assert body.status_code == 200, body.text
    training = next(f for f in body.json()["facilities"] if f["kind"] == "training")
    assert training["level"] == 1 and training["upgrading"]
    assert carousel.budget(db, team, season.year).payroll == before + 1_000_000
    again = client.post(url)
    assert again.status_code == 409 and "already being upgraded" in again.json()["detail"]
    facilities.complete_upgrades(db, league, season.year)
    facility = _facility(db, franchise.team_id, "training")
    assert facility.level == 2 and facility.upgrade_year is None
    # Next season: the upgrade's paid for; the upkeep goes on.
    assert carousel.budget(db, team, season.year + 1).payroll >= rules.upkeep(2)
    assert client.post(f"/api/teams/{franchise.team_id}/facilities/pool/upgrade"
                       ).status_code == 404


def test_an_upgrade_must_fit_the_budget(db: Session, client: TestClient, season: Season,
                                        franchise: Franchise, league: League):
    league.staff_budget = 5_000_000
    db.commit()
    refused = client.post(f"/api/teams/{franchise.team_id}/facilities/medical/upgrade")
    assert refused.status_code == 409 and "more than your staff budget" in refused.json()["detail"]


def test_a_budget_that_can_t_keep_up_loses_levels(db: Session, season: Season,
                                                  franchise: Franchise, league: League,
                                                  owner: User):
    _facility(db, franchise.team_id, "scouting").level = 5
    league.staff_budget = 10_000_000  # (less than salaries plus upkeep)
    db.flush()
    facilities.keep_up(db, league, season.year)
    assert _facility(db, franchise.team_id, "scouting").level < 5
    assert db.scalar(select(Notification.title).where(
        Notification.user_id == owner.id, Notification.kind == "staff")).startswith(
        "Your scouting department fell to level")


def test_ai_teams_build_in_the_offseason(db: Session, season: Season, franchise: Franchise,
                                         league: League):
    carousel.offseason(db, league, season)
    ai = db.scalar(select(Team.id).where(Team.league_id == league.id,
                                         Team.id != franchise.team_id))
    assert _facility(db, ai, "training").upgrade_year == season.year + 1
    assert _facility(db, franchise.team_id, "training").upgrade_year is None  # (ours: ours)


def test_facilities_add_to_the_staff_s_effects(db: Session, client: TestClient,
                                               season: Season, franchise: Franchise,
                                               league: League):
    for kind in rules.FACILITIES:
        _facility(db, franchise.team_id, kind).level = 5
    db.flush()
    crew = staff.by_team(db, league)
    built = facilities.levels(db, league)
    qb = db.scalar(select(Player).where(Player.team_id == franchise.team_id,
                                        Player.position == "QB"))
    plain = staff.development_factors(crew, qb)
    better = staff.development_factors(crew, qb, built)
    assert better[0] > plain[0] and better[1] < plain[1]
    scale, reports = draft.scouting(db, league.id, franchise.team_id)
    trainer = staff.coach(crew[franchise.team_id]["scout"])
    assert scale < rules.scout_scale(trainer) and reports > rules.scouting_reports(25, trainer)
    hurt = db.scalar(select(Player).where(Player.team_id == franchise.team_id))
    injuries.after_week(db, league.id, [{"player": hurt.id, "injury": "Torn hamstring",
                                         "weeks": 10}])
    medic = staff.coach(crew[franchise.team_id]["trainer"])
    assert hurt.injury_weeks == rules.layoff(10, medic, SEASON_ENDING, 5) < rules.layoff(
        10, medic, SEASON_ENDING)
    db.commit()
    body = client.get(f"/api/players/{hurt.id}/coaching").json()
    assert "(medical center level 5)" in body["injuries"]


def test_facilities_go_with_the_league_and_into_the_export(db: Session, season: Season,
                                                           league: League):
    from app.services import sharing
    from app.services.leagues import delete_league

    data = sharing.export_league(db, league)
    assert len(data["facilities"]) == len(league.teams) * len(rules.FACILITIES)
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(Facility.id)) is None
