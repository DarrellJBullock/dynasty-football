import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, undefer

from app.api.jobs import jobs_inline
from app.domain.positions import ROSTER_MAX
from app.models import Franchise, Game, Job, League, Player, PlayerGameStats, Season
from app.services import compaction, jobs
from app.services.games import game_detail, line_score
from app.services.teams import current_season


@pytest.fixture
def inline(client: TestClient) -> TestClient:
    client.app.dependency_overrides[jobs_inline] = lambda: True
    return client


@pytest.fixture
def small(client: TestClient, db: Session) -> League:
    """A 4-team league of the owner's (quick to play many seasons)."""
    spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
    created = client.post("/api/leagues", json=spec.json()).json()
    return db.get(League, created["league"]["id"])


def _sim_ahead(client: TestClient, league: League, seasons: int) -> dict:
    response = client.post(f"/api/leagues/{league.id}/jobs",
                           json={"kind": "sim_seasons", "seasons": seasons})
    assert response.status_code == 202, response.text
    return response.json()


def test_sims_ahead_seasons_with_the_franchise_on_autopilot(inline: TestClient, db: Session,
                                                            small: League):
    start = current_season(db, small.id).year
    job = _sim_ahead(inline, small, 3)
    assert job == {**job, "status": "done", "cancellable": True, "params": {"seasons": 3},
                   "result": {"from_year": start, "to_year": start + 2, "seasons": 3}}
    assert job["label"] == f"Season 3 of 3 · {start + 2} · Draft"
    assert job["progress"] == job["total"]
    # In the preseason three seasons on, with three champions crowned.
    season = current_season(db, small.id)
    assert (season.year, season.phase) == (start + 3, "preseason")
    seasons = db.scalars(select(Season).where(Season.league_id == small.id)).all()
    assert sum(s.champion_team_id is not None for s in seasons) == 3

    # The franchise was run like an AI team: re-signed, drafted, cut to 53, under the cap.
    franchise = db.scalar(select(Franchise).where(Franchise.league_id == small.id))
    roster = db.scalars(select(Player).where(Player.team_id == franchise.team_id)).all()
    assert len(roster) <= ROSTER_MAX
    assert sum(p.active_contract.salary for p in roster) <= small.salary_cap
    logs = [s.offseason_log for s in seasons if s.offseason_log]
    assert any(e["team"] == franchise.team_id for log in logs for e in log["re_signed"])
    assert any(e["team"] == franchise.team_id for log in logs for e in log.get("drafted", []))


def test_the_dynasty_report(inline: TestClient, db: Session, small: League):
    start = current_season(db, small.id).year
    _sim_ahead(inline, small, 2)
    report = inline.get(f"/api/leagues/{small.id}/dynasty?from_year={start}&to_year={start + 1}")
    assert report.status_code == 200, report.text
    body = report.json()
    assert [s["season"]["year"] for s in body["seasons"]] == [start, start + 1]  # oldest first
    first = body["seasons"][0]
    assert first["season"]["champion"] is not None
    assert first["season"]["franchise_record"] is not None
    # The offseason after it (its rookies may not all survive the cut to 53).
    assert (first["offseason"]["from_year"], first["offseason"]["year"]) == (start, start + 1)
    # Up to 10 seasons, in order.
    for query in (f"from_year={start}&to_year={start + 10}",
                  f"from_year={start + 1}&to_year={start}"):
        assert inline.get(f"/api/leagues/{small.id}/dynasty?{query}").status_code == 422


def test_stopping_between_weeks_and_carrying_on(db: Session, small: League):
    job = jobs.begin(db, jobs.enqueue(db, small, "sim_seasons", {"seasons": 2}))
    jobs.cancel(db, job)
    jobs.run(db, job)
    assert (job.status, job.progress) == ("cancelled", 1)
    assert job.label.startswith("Season 1 of 2 · ")
    season = current_season(db, small.id)
    assert (season.phase, season.current_week) == ("regular_season", 2)
    # The rest can be played from there.
    again = jobs.run(db, jobs.begin(db, jobs.enqueue(db, small, "sim_seasons", {"seasons": 1})))
    assert again.status == "done"
    assert current_season(db, small.id).year == season.year + 1


@pytest.mark.parametrize("body", [{"kind": "sim_seasons"}, {"kind": "sim_seasons", "seasons": 0},
                                  {"kind": "sim_seasons", "seasons": 11}])
def test_one_to_ten_seasons(client: TestClient, small: League, body: dict):
    assert client.post(f"/api/leagues/{small.id}/jobs", json=body).status_code == 422


def test_other_jobs_take_no_params(db: Session, small: League):
    job = jobs.enqueue(db, small, "sim_regular_season", {"seasons": 3})
    assert job.params is None


class TestCompaction:
    def test_older_seasons_keep_play_by_play_only_where_it_matters(
            self, inline: TestClient, db: Session, small: League):
        start = current_season(db, small.id).year
        _sim_ahead(inline, small, 1)
        first_season = db.scalar(select(Season).where(Season.league_id == small.id,
                                                      Season.year == start))
        franchise = db.scalar(select(Franchise).where(Franchise.league_id == small.id))
        first_season_lines = (select(func.count(PlayerGameStats.id)).join(Game)
                              .where(Game.season_id == first_season.id))
        stats_before = db.scalar(first_season_lines)
        games = {g.id: (line_score(g.play_log), g.home_score, g.away_score)
                 for g in db.scalars(select(Game).options(undefer(Game.play_log))
                                     .where(Game.season_id == first_season.id))}
        # A season later, the first season is older than "last season".
        _sim_ahead(inline, small, 1)
        compacted = db.scalars(select(Game).where(Game.season_id == first_season.id,
                                                  Game.log_compacted.is_(True))).all()
        kept = db.scalars(select(Game).where(Game.season_id == first_season.id,
                                             Game.log_compacted.is_(False))).all()
        assert compacted
        assert all(franchise.team_id not in (g.home_team_id, g.away_team_id)
                   and g.stage == "regular" for g in compacted)
        assert all(franchise.team_id in (g.home_team_id, g.away_team_id)
                   or g.stage == "playoff" for g in kept)
        # The box score page is unchanged: line score, scores, and the stat lines.
        for game in compacted:
            detail = game_detail(db, game)
            assert detail.log_compacted
            assert (detail.line_score, game.home_score, game.away_score) == games[game.id]
        assert db.scalar(first_season_lines) == stats_before
        # Nothing to watch.
        playback = inline.get(f"/api/games/{compacted[0].id}/playback").json()
        assert playback["log_compacted"] is True and playback["plays"] == []
        # The last season and the current one are untouched.
        assert db.scalar(select(func.count(Game.id)).join(Season).where(
            Season.league_id == small.id, Season.year > start, Game.log_compacted)) == 0

    def test_a_compacted_log_keeps_scores_injuries_and_the_last_play(self):
        def play(home, away, quarter, events=()):
            return {"score": {"home": home, "away": away}, "quarter": quarter,
                    "events": list(events)}
        log = [play(0, 0, 1), play(7, 0, 1), play(7, 0, 2, [{"t": "injury"}]),
               play(7, 0, 3), play(7, 3, 4), play(7, 3, 4)]
        kept = compaction.compact_log(log)
        assert kept == [log[1], log[2], log[4], log[5]]
        assert line_score(kept) == line_score(log)


def test_the_league_lock_covers_sim_ahead(client: TestClient, db: Session, small: League):
    _sim_ahead(client, small, 2)  # (queued: no worker in tests)
    assert db.scalar(select(Job.status).where(Job.league_id == small.id)) == "queued"
    season = current_season(db, small.id)
    assert client.post(f"/api/seasons/{season.id}/simulate",
                       json={"until": "next_week"}).status_code == 409
