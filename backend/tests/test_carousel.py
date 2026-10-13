"""Milestone 12, part 4: the coaching carousel and the staff budget
(docs/design/staff-and-legacy.md §3)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import staff as rules
from app.models import (
    Franchise,
    League,
    Notification,
    Season,
    StaffDeadMoney,
    StaffMember,
    StaffSeason,
    Team,
    User,
)
from app.services import carousel, staff

# ---------- the rules ----------

def test_staff_retire_late_and_surely():
    assert rules.retire_chance(60) == 0 and rules.retire_chance(61) == 0
    assert rules.retire_chance(62) == pytest.approx(0.12)
    assert rules.retire_chance(70) == 1.0


def test_ai_teams_keep_good_staff_who_aren_t_too_old():
    assert rules.ai_keeps(75, 50) and not rules.ai_keeps(55, 50) and not rules.ai_keeps(80, 66)


def test_the_best_hire_the_budget_allows():
    pool = [(1, 90, 50, 9_000_000), (2, 80, 40, 6_000_000), (3, 80, 35, 6_000_000),
            (4, 55, 60, 3_000_000)]
    assert rules.best_hire(pool, 7_000_000) == 3  # (80s fit; the younger)
    assert rules.best_hire(pool, 10_000_000) == 1
    assert rules.best_hire(pool, 1_000_000) == 4  # (none fits: the cheapest)
    assert rules.best_hire([], 5_000_000) is None


# ---------- in a league ----------

@pytest.fixture
def season(db: Session, league: League) -> Season:
    staff.ensure_staff(db, league)
    db.commit()
    return league.seasons[0]


def _member(db: Session, team_id: int, role: str) -> StaffMember:
    return db.scalar(select(StaffMember).where(StaffMember.team_id == team_id,
                                               StaffMember.role == role))


def _free(db: Session, league: League, role: str, rating: int = 70) -> StaffMember:
    member = StaffMember(league_id=league.id, team_id=None, role=role, first_name="Free",
                         last_name="Agent", age=45, rating=rating, specialty=None,
                         salary=rules.salary(role, rating), contract_end=0)
    db.add(member)
    db.flush()
    return member


class TestTheBudget:
    def test_payroll_is_salaries_and_dead_money(self, db: Session, season: Season,
                                                franchise: Franchise):
        team = db.get(Team, franchise.team_id)
        salaries = db.scalar(select(func.sum(StaffMember.salary)).where(
            StaffMember.team_id == team.id))
        view = carousel.budget(db, team, season.year)
        assert view.payroll == salaries and view.dead_money == 0
        assert view.room == view.budget - salaries
        db.add(StaffDeadMoney(team_id=team.id, staff_id=_member(db, team.id, "scout").id,
                              year=season.year, amount=500_000))
        assert carousel.budget(db, team, season.year).payroll == salaries + 500_000


class TestAManagersMoves:
    def test_fire_then_hire_from_the_market(self, db: Session, client: TestClient,
                                            season: Season, franchise: Franchise, league: League):
        scout = _member(db, franchise.team_id, "scout")
        scout.contract_end = season.year + 1
        db.commit()
        fired = client.post(f"/api/staff/{scout.id}/fire")
        assert fired.status_code == 200, fired.text
        assert fired.json()["vacancies"] == ["scout"]
        owed = db.scalars(select(StaffDeadMoney).where(StaffDeadMoney.staff_id == scout.id)).all()
        assert sorted(d.year for d in owed) == [season.year, season.year + 1]
        assert fired.json()["budget"]["dead_money"] == scout.salary
        market = client.get(f"/api/leagues/{league.id}/staff-market").json()
        assert scout.id in [c["id"] for c in market["candidates"]]
        new = _free(db, league, "scout", 80)
        db.commit()
        hired = client.post(f"/api/teams/{franchise.team_id}/staff/hire",
                            json={"staff_id": new.id, "years": 2})
        assert hired.status_code == 200, hired.text
        assert hired.json()["vacancies"] == []
        assert new.team_id == franchise.team_id and new.contract_end == season.year + 1
        assert new.salary == rules.salary("scout", 80)

    def test_a_hire_needs_an_open_job_and_room(self, db: Session, client: TestClient,
                                               season: Season, franchise: Franchise,
                                               league: League):
        candidate = _free(db, league, "head_coach", 95)
        db.commit()
        url = f"/api/teams/{franchise.team_id}/staff/hire"
        taken = client.post(url, json={"staff_id": candidate.id})
        assert taken.status_code == 409 and "already have a head coach" in taken.json()["detail"]
        head = _member(db, franchise.team_id, "head_coach")
        client.post(f"/api/staff/{head.id}/fire")
        league.staff_budget = 5_000_000
        db.commit()
        poor = client.post(url, json={"staff_id": candidate.id})
        assert poor.status_code == 409 and "more than your staff budget" in poor.json()["detail"]
        assert client.post(url, json={"staff_id": head.id, "years": 9}).status_code == 422

    def test_extending_in_the_final_season(self, db: Session, client: TestClient,
                                           season: Season, franchise: Franchise):
        trainer = _member(db, franchise.team_id, "trainer")
        trainer.contract_end = season.year + 2
        db.commit()
        early = client.post(f"/api/staff/{trainer.id}/extend", json={"years": 2})
        assert early.status_code == 409 and "final season" in early.json()["detail"]
        trainer.contract_end = season.year
        db.commit()
        assert client.post(f"/api/staff/{trainer.id}/extend",
                           json={"years": 3}).status_code == 200
        assert trainer.contract_end == season.year + 3

    def test_only_the_team_s_manager_or_a_commissioner(self, db: Session, season: Season,
                                                       franchise: Franchise, league: League):
        from app.services import accounts, members
        from tests.conftest import make_client, sign_in_as

        owner = db.scalar(select(User).where(User.id == league.user_id))
        user = accounts.sign_up(db, "friend@example.test", "friend-password")
        _invite, token = members.create_invite(db, league, owner)
        theirs = db.scalar(select(Team).where(Team.league_id == league.id,
                                              Team.id != franchise.team_id).order_by(Team.id))
        members.join(db, token, user, theirs.id)
        db.commit()
        with make_client(db) as other:
            sign_in_as(other, db, user)
            mine = _member(db, franchise.team_id, "scout")
            assert other.post(f"/api/staff/{mine.id}/fire").status_code == 403
            assert other.post(f"/api/teams/{franchise.team_id}/staff/hire",
                              json={"staff_id": mine.id}).status_code == 403


class TestTheOffseason:
    def test_the_carousel_turns(self, db: Session, season: Season, franchise: Franchise,
                                league: League, owner: User):
        ai = db.scalar(select(Team).where(Team.league_id == league.id,
                                          Team.id != franchise.team_id).order_by(Team.id))
        # An AI head coach two seasons in, after a losing one: fired.
        head = _member(db, ai.id, "head_coach")
        head.contract_end = season.year + 2
        db.add(StaffSeason(staff_id=head.id, season_id=season.id, team_id=ai.id,
                           role="head_coach", wins=3, losses=14, ties=0))
        older = Season(league_id=league.id, year=season.year - 1, phase="offseason")
        db.add(older)
        db.flush()
        db.add(StaffSeason(staff_id=head.id, season_id=older.id, team_id=ai.id,
                           role="head_coach", wins=4, losses=13, ties=0))
        # An AI team's good coordinator whose contract ends: kept.
        good = _member(db, ai.id, "offensive_coordinator")
        good.contract_end, good.rating, good.age = season.year, 82, 45
        # An old AI scout: retires.
        old = _member(db, ai.id, "scout")
        old.age = 75
        # Our coordinator's contract ends: he leaves, and we hear about it.
        ours = _member(db, franchise.team_id, "defensive_coordinator")
        ours.contract_end, ours.rating, ours.age = season.year, 85, 45
        db.flush()
        free_before = db.scalar(select(func.count(StaffMember.id)).where(
            StaffMember.team_id.is_(None)))
        carousel.offseason(db, league, season)
        assert head.team_id != ai.id
        assert sorted(d.year for d in db.scalars(select(StaffDeadMoney).where(
            StaffDeadMoney.staff_id == head.id))) == [season.year + 1, season.year + 2]
        assert good.team_id == ai.id and good.contract_end > season.year
        assert old.retired_year == season.year and old.team_id is None
        assert ours.team_id is None
        assert f"Defensive coordinator {ours.full_name}'s contract ended" in db.scalars(
            select(Notification.title).where(Notification.user_id == owner.id,
                                             Notification.kind == "staff")).all()
        # New staff came onto the market, and AI teams filled every job; ours stays open.
        assert db.scalar(select(func.count(StaffMember.id)).where(
            StaffMember.league_id == league.id)) > free_before
        for role in rules.ROLES:
            assert _member(db, ai.id, role) is not None
        assert _member(db, franchise.team_id, "defensive_coordinator") is None

    def test_on_autopilot_our_team_is_run_like_an_ai_s(self, db: Session, season: Season,
                                                       franchise: Franchise, league: League):
        ours = _member(db, franchise.team_id, "defensive_coordinator")
        ours.contract_end, ours.rating, ours.age = season.year, 85, 45
        carousel.offseason(db, league, season, autopilot=True)
        assert ours.team_id == franchise.team_id and ours.contract_end > season.year

    def test_the_preseason_fills_our_open_jobs(self, db: Session, season: Season,
                                               franchise: Franchise, league: League,
                                               owner: User):
        ours = _member(db, franchise.team_id, "trainer")
        carousel.fire(db, ours)
        _free(db, league, "trainer", 60)
        hired = carousel.fill_vacancies(db, league, season.year)
        assert [m.team_id for m in hired] == [franchise.team_id]
        assert db.scalar(select(Notification.title).where(
            Notification.user_id == owner.id, Notification.kind == "staff")).endswith(
            "is your interim head trainer")


def test_the_staff_budget_setting(client: TestClient, league: League):
    url = f"/api/leagues/{league.id}/settings"
    assert client.patch(url, json={"staff_budget": 1_000}).status_code == 422
    assert client.patch(url, json={"staff_budget": 30_000_000}).json()[
        "staff_budget"] == 30_000_000
