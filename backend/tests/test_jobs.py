from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.jobs import jobs_inline
from app.models import Franchise, Game, Job, League, Season
from app.services import jobs
from app.worker import run_once


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def inline(client: TestClient) -> TestClient:
    """Jobs run inside the request, as a worker would run them."""
    client.app.dependency_overrides[jobs_inline] = lambda: True
    return client


def _start(client: TestClient, league: League, kind: str) -> dict:
    response = client.post(f"/api/leagues/{league.id}/jobs", json={"kind": kind})
    assert response.status_code == 202, response.text
    return response.json()


class TestRunningJobs:
    def test_the_regular_season_as_a_job(self, inline: TestClient, league: League,
                                         season: Season):
        job = _start(inline, league, "sim_regular_season")
        assert job == {**job, "status": "done", "progress": 17, "total": 17,
                       "label": "Week 17 of 17", "cancellable": True, "error": None}
        # The result is what the synchronous endpoint returns.
        result = job["result"]
        assert result["weeks_simulated"] == 17
        assert result["games_simulated"] == 16 * 17
        assert len(result["franchise_games"]) == 17
        assert result["season"]["phase"] == "playoffs"
        assert inline.get(f"/api/jobs/{job['id']}").json() == job

    def test_a_whole_season_and_offseason_as_jobs(self, inline: TestClient, db: Session,
                                                  league: League, season: Season):
        _start(inline, league, "sim_regular_season")
        playoffs = _start(inline, league, "sim_playoffs")
        rounds = len(inline.get(f"/api/leagues/{league.id}/playoffs").json()["rounds"])
        assert playoffs == {**playoffs, "status": "done", "total": rounds, "progress": rounds,
                            "label": "Championship"}
        assert playoffs["result"]["season"]["champion"] is not None

        offseason = _start(inline, league, "advance_offseason")
        assert offseason == {**offseason, "status": "done", "total": 1, "cancellable": False}
        assert offseason["result"]["phase"] == "free_agency"

        market = _start(inline, league, "finish_free_agency")
        assert market == {**market, "status": "done", "total": 5, "label": "Day 5 of 5"}
        assert market["result"]["season"]["phase"] == "draft"
        assert market["result"]["signings"]

        drafted = _start(inline, league, "finish_draft")
        assert drafted["status"] == "done"
        assert drafted["result"]["season"]["phase"] == "preseason"
        assert len(drafted["result"]["picks"]) > 0

    def test_a_job_that_cant_run_fails_with_the_reason(self, inline: TestClient,
                                                       league: League, season: Season):
        job = _start(inline, league, "sim_playoffs")
        assert job["status"] == "failed"
        assert "regular season" in job["error"]
        assert job["result"] is None
        # The league is free again.
        assert _start(inline, league, "sim_regular_season")["status"] == "done"

    def test_unknown_kinds_and_jobs(self, client: TestClient, league: League):
        assert client.post(f"/api/leagues/{league.id}/jobs",
                           json={"kind": "sim_forever"}).status_code == 422
        assert client.post("/api/leagues/999999/jobs",
                           json={"kind": "sim_playoffs"}).status_code == 404
        assert client.get("/api/jobs/999999").status_code == 404
        assert client.delete("/api/jobs/999999").status_code == 404


class TestTheLeagueLock:
    def test_a_queued_job_locks_the_league_until_it_ends(
            self, client: TestClient, db: Session, league: League, season: Season,
            franchise: Franchise):
        job = _start(client, league, "sim_regular_season")
        assert job == {**job, "status": "queued", "progress": 0, "total": 17,
                       "label": "Simulating the season"}
        # One job per league.
        again = client.post(f"/api/leagues/{league.id}/jobs", json={"kind": "sim_playoffs"})
        assert again.status_code == 409
        # Changes wait; reads don't, and the season shows the job.
        blocked = client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
        assert blocked.status_code == 409
        assert "simulation is running" in blocked.json()["detail"]
        roster = client.get(f"/api/teams/{franchise.team_id}/roster").json()
        assert client.post(f"/api/players/{roster[0]['id']}/release").status_code == 409
        assert client.delete(f"/api/teams/{franchise.team_id}/depth-chart").status_code == 409
        dashboard = client.get("/api/franchise/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["franchise"]["season"]["active_job"]["id"] == job["id"]

        cancelled = client.delete(f"/api/jobs/{job['id']}").json()
        assert cancelled["status"] == "cancelled"
        assert client.get("/api/franchise").json()["season"]["active_job"] is None
        assert client.post(f"/api/seasons/{season.id}/simulate",
                           json={"until": "next_week"}).status_code == 200

    def test_other_leagues_are_not_locked(self, client: TestClient, league: League):
        _start(client, league, "sim_regular_season")
        response = client.post("/api/leagues", json=client.get(
            "/api/leagues/template?conferences=1&divisions=1&teams_per_division=4").json())
        assert response.status_code == 201, response.text


class TestTheWorker:
    def test_cancelling_stops_between_weeks(self, db: Session, league: League, season: Season):
        job = jobs.begin(db, jobs.enqueue(db, league, "sim_regular_season"))
        jobs.cancel(db, job)
        assert job.status == "running" and job.cancel_requested
        jobs.run(db, job)
        assert (job.status, job.progress, job.label) == ("cancelled", 1, "Week 1 of 17")
        assert season.current_week == 2
        assert db.scalar(select(func.count(Game.id)).where(
            Game.season_id == season.id, Game.status == "final")) == 16
        # The rest can be played from there.
        assert jobs.run(db, jobs.begin(db, jobs.enqueue(
            db, league, "sim_regular_season"))).progress == 16

    def test_one_step_jobs_finish_once_started(self, db: Session, league: League,
                                               season: Season):
        season.phase = "offseason"
        job = jobs.begin(db, jobs.enqueue(db, league, "advance_offseason"))
        jobs.cancel(db, job)
        assert jobs.run(db, job).status == "done"

    def test_runs_the_oldest_queued_job(self, db: Session, league: League, season: Season):
        job = jobs.enqueue(db, league, "sim_regular_season")
        assert run_once(lambda: nullcontext(db)) is True
        assert job.status == "done" and job.started_at and job.finished_at
        assert run_once(lambda: nullcontext(db)) is False

    def test_jobs_whose_worker_died_fail(self, db: Session, league: League, season: Season):
        job = jobs.begin(db, jobs.enqueue(db, league, "sim_regular_season"))
        assert jobs.reap_stale(db) == 0
        assert jobs.reap_stale(db, now=datetime.now(UTC) + timedelta(minutes=2)) == 1
        db.refresh(job)
        assert job.status == "failed" and "stopped unexpectedly" in job.error
        assert jobs.enqueue(db, league, "sim_regular_season").status == "queued"


def test_deleting_a_league_deletes_its_jobs(client: TestClient, db: Session):
    spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
    created = client.post("/api/leagues", json=spec.json()).json()
    other = db.get(League, created["league"]["id"])
    finished = jobs.enqueue(db, other, "sim_playoffs")
    jobs.run(db, jobs.begin(db, finished))  # (fails: no playoffs yet) and ends
    first = db.scalars(select(Franchise).order_by(Franchise.id)).first()
    client.post(f"/api/franchises/{first.id}/activate")
    assert client.delete(f"/api/leagues/{other.id}").status_code == 204
    assert db.scalar(select(func.count(Job.id)).where(Job.league_id == other.id)) == 0
