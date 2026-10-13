"""Milestone 14, part 3: job security (docs/design/owners-and-front-offices.md §4)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import owners as owner_rules
from app.models import (
    Franchise,
    GmStint,
    League,
    Notification,
    Owner,
    OwnerSeason,
    Season,
    Team,
    User,
)
from app.schemas import SimulateRequest
from app.services import accounts, careers, members, offseason
from app.services import season as season_service
from app.services.members import human_team_ids


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def everyone_fired(monkeypatch):
    """Every owner ends the season below the line (whatever the results)."""
    monkeypatch.setattr(owner_rules, "FIRE_LINE", 101)


def _finish(db: Session, season: Season) -> None:
    season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"))
    while season.phase == "playoffs":
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
    db.commit()


def _friend(db: Session, owner: User, league: League, franchise: Franchise) -> Franchise:
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id.desc()))
    joined = members.join(db, token, user, team.id)
    db.commit()
    return joined


class TestWhoCanBeFired:
    def test_the_rule(self, league: League):
        alone, friends = {1}, {1, 2}
        league.firing = "auto"
        assert careers.fires(league, 9, friends)  # (an AI team's GM)
        assert careers.fires(league, 1, alone) and not careers.fires(league, 1, friends)
        league.firing = "on"
        assert careers.fires(league, 1, friends)
        league.firing = "off"
        assert not careers.fires(league, 1, alone) and not careers.fires(league, 9, alone)

    def test_the_commissioner_sets_it_between_seasons(self, client: TestClient, league: League):
        url = f"/api/leagues/{league.id}/rules"
        assert client.get(url).json()["firing"] == "auto"
        assert client.patch(url, json={"firing": "off"}).json()["firing"] == "off"
        assert client.patch(url, json={"firing": "never"}).status_code == 422


class TestFiring:
    def test_an_ai_gm_is_replaced_at_once(self, db: Session, everyone_fired, league: League,
                                          franchise: Franchise, season: Season):
        _finish(db, season)
        ai = db.scalar(select(OwnerSeason).where(OwnerSeason.season_id == season.id,
                                                 OwnerSeason.team_id != franchise.team_id))
        assert ai.fired and ai.verdict == "has had enough"
        owner = db.scalar(select(Owner).where(Owner.team_id == ai.team_id))
        assert owner.confidence == owner_rules.START_CONFIDENCE  # (a new general manager)

    def test_a_member_is_fired_and_must_choose_a_new_job(
            self, db: Session, client: TestClient, everyone_fired, league: League,
            franchise: Franchise, season: Season, owner: User):
        _finish(db, season)
        db.refresh(franchise)
        assert franchise.fired_at is not None
        assert db.scalar(select(Notification.title).where(
            Notification.user_id == owner.id, Notification.kind == "job")).startswith(
            "You've been fired by the")
        with pytest.raises(Exception, match="choose their next job first"):
            offseason.advance(db, season)
        db.rollback()

        career = client.get("/api/franchise/career").json()
        assert career["fired"] and len(career["open_jobs"]) >= careers.MIN_JOBS
        assert franchise.team_id not in [j["team"]["id"] for j in career["open_jobs"]]
        job = career["open_jobs"][0]
        assert job["why"] == "The owner just fired the general manager."
        assert job["situation"] in owner_rules.SITUATIONS and job["owner"]

        old = franchise.team_id
        taken = client.post("/api/franchise/take-job", json={"team_id": job["team"]["id"]})
        assert taken.status_code == 200, taken.text
        body = taken.json()
        assert not body["fired"] and body["team"]["id"] == job["team"]["id"]
        assert [s["team"]["id"] for s in body["stints"]] == [old, job["team"]["id"]]
        first, second = body["stints"]
        assert first["ended"] == "fired" and first["to_year"] == season.year
        assert first["seasons"] == 1 and first["wins"] + first["losses"] + first["ties"] > 0
        assert second["from_year"] == season.year + 1 and second["seasons"] == 0
        assert body["firings"] == 1
        db.expire_all()
        assert human_team_ids(db, league.id) == {job["team"]["id"]}  # (the old team: the AI's)
        for tid in (old, job["team"]["id"]):
            assert db.scalar(select(Owner.confidence).where(Owner.team_id == tid)) == 60
        assert client.get("/api/franchise").json()["team"]["id"] == job["team"]["id"]
        offseason.advance(db, season)  # (now the offseason can begin)

    def test_only_a_fired_member_and_only_an_open_job(self, db: Session, client: TestClient,
                                                      franchise: Franchise, season: Season):
        refused = client.post("/api/franchise/take-job", json={"team_id": franchise.team_id})
        assert refused.status_code == 409 and "haven't been fired" in refused.json()["detail"]

    def test_with_friends_members_keep_their_jobs_unless_the_commissioner_says(
            self, db: Session, client: TestClient, everyone_fired, owner: User, league: League,
            franchise: Franchise, season: Season):
        friend = _friend(db, owner, league, franchise)
        _finish(db, season)
        db.expire_all()
        assert franchise.fired_at is None and db.get(Franchise, friend.id).fired_at is None
        rows = db.scalars(select(OwnerSeason).where(OwnerSeason.season_id == season.id)).all()
        assert sum(r.fired for r in rows) == len(rows) - 2  # (every AI team's)

    def test_on_autopilot_the_owner_keeps_you(self, db: Session, everyone_fired,
                                              franchise: Franchise, season: Season):
        _finish(db, season)
        offseason.advance(db, season, autopilot=True)
        db.refresh(franchise)
        assert franchise.fired_at is None
        assert db.scalar(select(Owner.confidence).where(Owner.team_id == franchise.team_id)) == 60

    def test_a_rolled_back_final_unfires_but_not_after_a_new_job(
            self, db: Session, client: TestClient, everyone_fired, league: League,
            franchise: Franchise, season: Season):
        _finish(db, season)
        assert client.post(f"/api/leagues/{league.id}/rollback").status_code == 200
        db.expire_all()
        assert franchise.fired_at is None
        assert not any(r.fired for r in db.scalars(select(OwnerSeason)))
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        db.commit()
        job = client.get("/api/franchise/career").json()["open_jobs"][0]
        client.post("/api/franchise/take-job", json={"team_id": job["team"]["id"]})
        refused = client.post(f"/api/leagues/{league.id}/rollback")
        assert refused.status_code == 409 and "another job" in refused.json()["detail"]


def test_a_career_from_the_first_season(db: Session, client: TestClient, franchise: Franchise,
                                        season: Season):
    career = client.get("/api/franchise/career").json()
    assert not career["fired"] and career["open_jobs"] == [] and career["firings"] == 0
    assert [(s["team"]["id"], s["from_year"], s["to_year"]) for s in career["stints"]] == [
        (franchise.team_id, season.year, None)]
    assert db.scalar(select(GmStint.id)) is None  # (nothing stored until a move)
