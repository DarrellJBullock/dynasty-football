"""Milestone 12, part 2: staff (docs/design/staff-and-legacy.md §3)."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.models import Franchise, League, Season, StaffMember, StaffSeason, Team
from app.seed import data
from app.services import offseason, sharing, staff

# ---------- the rules ----------

def test_staff_are_made_within_their_role_s_bounds():
    rng = random.Random(1)
    for role in rules.ROLES:
        for _ in range(200):
            made = rules.make(rng, role)
            low, high = rules.AGES[role]
            assert low <= made.age <= high
            assert rules.RATING_MIN <= made.rating <= rules.RATING_MAX
            assert 1 <= made.years <= 4
            specialties = rules.SPECIALTIES[role]
            assert (made.specialty in specialties) if specialties else made.specialty is None


def test_better_staff_cost_more_and_head_coaches_most():
    assert rules.salary("head_coach", 90) > rules.salary("head_coach", 60)
    assert rules.salary("head_coach", 70) > rules.salary("offensive_coordinator", 70) \
        > rules.salary("scout", 70)
    assert rules.salary("scout", 40) == rules.SALARY_BASE["scout"]  # (no less than the base)


def test_coach_of_the_year_is_the_biggest_turnaround():
    c = rules.CoachSeason
    assert rules.coach_of_the_year([c(1, 13, 12), c(2, 10, 4), c(3, 9, 3)]) == 2  # +6 ties +6
    assert rules.coach_of_the_year([c(1, 11, None), c(2, 9, 9)]) == 1  # (no season before)
    assert rules.coach_of_the_year([]) is None


# ---------- staff in a league ----------

def test_every_team_gets_a_staff_once_the_same_way(db: Session, league: League):
    staff.ensure_staff(db, league)
    members = db.scalars(select(StaffMember).where(StaffMember.league_id == league.id)
                         .order_by(StaffMember.id)).all()
    assert len(members) == len(league.teams) * len(rules.ROLES)
    for team in league.teams:
        assert sorted(m.role for m in members if m.team_id == team.id) == sorted(rules.ROLES)
    names = [(m.full_name, m.role, m.rating) for m in members]
    staff.ensure_staff(db, league)  # (once)
    assert db.scalar(select(func.count(StaffMember.id))) == len(members)
    for m in members:
        db.delete(m)
    db.flush()
    staff.ensure_staff(db, league)
    again = db.scalars(select(StaffMember).order_by(StaffMember.id)).all()
    assert [(m.full_name, m.role, m.rating) for m in again] == names  # (its own seed)


def test_a_team_has_one_of_each_role(db: Session, league: League):
    """A request that raced another to make the staff would fail, not double it."""
    from sqlalchemy.exc import IntegrityError

    staff.ensure_staff(db, league)
    team = league.teams[0]
    db.add(StaffMember(league_id=league.id, team_id=team.id, role="head_coach",
                       first_name="Extra", last_name="Coach", age=50, rating=60,
                       salary=1, contract_end=2030))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_new_league_has_its_staff_from_the_start(client: TestClient, db: Session):
    spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
    made = client.post("/api/leagues", json={**spec.json(), "players": "women"}).json()
    members = db.scalars(select(StaffMember).where(
        StaffMember.league_id == made["league"]["id"])).all()
    assert len(members) == 4 * len(rules.ROLES)
    assert all(m.first_name in data.FIRST_NAMES_WOMEN for m in members)


def test_the_staff_page_and_the_league_s_coaches(client: TestClient, franchise: Franchise,
                                                 league: League):
    view = client.get(f"/api/teams/{franchise.team_id}/staff").json()
    assert [m["role"] for m in view["members"]] == list(rules.ROLES)
    head = view["members"][0]
    assert head["role_label"] == "Head coach" and head["duty"]
    assert head["salary"] == rules.salary("head_coach", head["rating"])
    assert view["payroll"] == sum(m["salary"] for m in view["members"])
    assert head["career"]["seasons"] == 0
    coaches = client.get(f"/api/leagues/{league.id}/coaches").json()
    assert len(coaches["head_coaches"]) == len(league.teams)
    assert coaches["coach_of_the_year"] == []


@pytest.fixture
def finished(client: TestClient, league: League) -> Season:
    season = league.seasons[0]
    sim = f"/api/seasons/{season.id}/simulate"
    client.post(sim, json={"until": "end_of_regular_season"})
    client.post(sim, json={"until": "end_of_playoffs"})
    return season


def test_a_season_goes_on_every_staff_member_s_record(client: TestClient, db: Session,
                                                      finished: Season, league: League):
    rows = db.scalars(select(StaffSeason).where(StaffSeason.season_id == finished.id)).all()
    assert len(rows) == len(league.teams) * len(rules.ROLES)
    champion = [r for r in rows if r.champion]
    assert {r.team_id for r in champion} == {finished.champion_team_id}
    assert all(r.playoff_wins >= 1 for r in champion)
    coy = [r for r in rows if r.coach_of_the_year]
    assert len(coy) == 1 and coy[0].role == "head_coach"
    # A first season: no turnaround to measure, so the most wins.
    heads = [r for r in rows if r.role == "head_coach"]
    assert coy[0].wins == max(r.wins for r in heads)
    coaches = client.get(f"/api/leagues/{league.id}/coaches").json()
    assert coaches["coach_of_the_year"][0]["year"] == finished.year
    best = coaches["head_coaches"][0]
    assert best["career"]["seasons"] == 1 and best["career"]["wins"] == max(r.wins for r in heads)
    staff.record_season(db, finished)  # (once)
    assert db.scalar(select(func.count(StaffSeason.id))) == len(rows)


def test_the_offseason_ages_the_staff(db: Session, league: League):
    staff.ensure_staff(db, league)
    ages = dict(db.execute(select(StaffMember.id, StaffMember.age)).all())
    season = league.seasons[0]
    season.phase = "offseason"
    offseason.advance(db, season)
    assert all(m.age == ages[m.id] + 1 for m in db.scalars(select(StaffMember)))


def test_staff_go_with_the_league_and_into_the_export(db: Session, league: League):
    from app.services.leagues import delete_league

    staff.ensure_staff(db, league)
    data_out = sharing.export_league(db, league)
    assert len(data_out["staff"]) == len(league.teams) * len(rules.ROLES)
    assert "staff_seasons" in data_out
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(func.count(StaffMember.id))) == 0
    assert db.scalar(select(func.count(Team.id))) == 0
