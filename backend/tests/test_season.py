import dataclasses

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Franchise, Game, League, PlayerGameStats, Season, TeamGameStats
from app.services.season import game_seed
from app.sim.stats import PlayerLine, TeamLine


@pytest.fixture
def season(db: Session, league: League) -> Season:
    return league.seasons[0]


def _simulate(client: TestClient, season: Season, until: str = "next_week"):
    return client.post(f"/api/seasons/{season.id}/simulate", json={"until": until})


def test_stats_tables_mirror_the_engine_box_score():
    assert {c for c in PlayerGameStats.__table__.columns.keys()} >= {
        f.name for f in dataclasses.fields(PlayerLine)}
    assert {c for c in TeamGameStats.__table__.columns.keys()} >= {
        f.name for f in dataclasses.fields(TeamLine)}


def test_game_seed_is_stable_and_distinct():
    assert game_seed(1, 2026, 1, 10) == game_seed(1, 2026, 1, 10)
    assert game_seed(1, 2026, 1, 10) != game_seed(1, 2026, 1, 11)


class TestSimulateWeek:
    def test_plays_one_week_and_stores_everything(self, client: TestClient, db: Session,
                                                  season: Season, franchise: Franchise):
        response = _simulate(client, season)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["weeks_simulated"] == 1
        assert body["games_simulated"] == 16
        assert body["season"] == {**body["season"], "phase": "regular_season",
                                  "current_week": 2, "regular_season_complete": False}
        assert len(body["franchise_games"]) == 1

        week1 = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1)).all()
        assert all(g.status == "final" and g.play_log and g.seed for g in week1)
        assert db.scalar(select(func.count(Game.id)).where(
            Game.season_id == season.id, Game.status == "final")) == 16
        for game in week1:
            team_rows = db.scalars(select(TeamGameStats).where(TeamGameStats.game_id == game.id))
            points = {row.team_id: row.points for row in team_rows}
            assert points == {game.home_team_id: game.home_score,
                              game.away_team_id: game.away_score}

    def test_standings_and_dashboard_follow_results(self, client: TestClient, season: Season,
                                                    league: League):
        _simulate(client, season)
        standings = client.get(f"/api/leagues/{league.id}/standings").json()
        rows = [row for division in standings for row in division["rows"]]
        assert sum(r["wins"] + r["losses"] + r["ties"] for r in rows) == 32
        dashboard = client.get("/api/franchise/dashboard").json()
        assert sum(dashboard["record"].values()) == 1
        assert len(dashboard["recent_games"]) == 1
        assert dashboard["recent_games"][0]["status"] == "final"
        assert dashboard["upcoming_games"][0]["week"] == 2

    def test_results_are_reproducible(self, client: TestClient, db: Session, season: Season):
        from app.services.season import league_sim_teams, play_game
        # Snapshot the rosters first: the week's injuries change them afterwards.
        sim_teams = league_sim_teams(db, season.league_id)
        _simulate(client, season)
        first = {g.id: (g.home_score, g.away_score) for g in db.scalars(
            select(Game).where(Game.season_id == season.id, Game.week == 1))}
        # Re-simulating the same week with the same rosters gives identical results.
        for game in db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1)):
            db.execute(TeamGameStats.__table__.delete().where(TeamGameStats.game_id == game.id))
            db.execute(PlayerGameStats.__table__.delete().where(
                PlayerGameStats.game_id == game.id))
            play_game(db, game, sim_teams, season.league_id, season.year)
            assert (game.home_score, game.away_score) == first[game.id]

    def test_depth_chart_and_injuries_are_used(self, client: TestClient, db: Session,
                                               season: Season, franchise: Franchise):
        roster = client.get(f"/api/teams/{franchise.team_id}/roster").json()
        starter = next(p for p in roster if p["position"] == "QB")
        client.patch(f"/api/players/{starter['id']}", json={"injury_status": "out"})
        _simulate(client, season)
        played = db.scalar(select(func.count(PlayerGameStats.id)).where(
            PlayerGameStats.player_id == starter["id"]))
        assert played == 0
        passing = db.scalars(select(PlayerGameStats).where(
            PlayerGameStats.team_id == franchise.team_id, PlayerGameStats.pass_att > 0)).all()
        assert passing and all(row.player_id != starter["id"] for row in passing)


class TestFullSeason:
    def test_simulates_to_the_end_then_stops(self, client: TestClient, db: Session,
                                             season: Season, league: League):
        body = _simulate(client, season, "end_of_regular_season").json()
        assert body["weeks_simulated"] == 17
        assert body["games_simulated"] == 16 * 17
        assert body["season"]["regular_season_complete"] is True
        assert len(body["franchise_games"]) == 17

        standings = client.get(f"/api/leagues/{league.id}/standings").json()
        assert all(r["wins"] + r["losses"] + r["ties"] == 17
                   for d in standings for r in d["rows"])
        # The regular season can't be simmed again; "next week" now means the playoffs.
        again = _simulate(client, season, "end_of_regular_season")
        assert again.status_code == 409
        assert "complete" in again.json()["detail"]
        assert body["season"]["phase"] == "playoffs"

    def test_partial_then_rest_of_season(self, client: TestClient, season: Season):
        _simulate(client, season)
        _simulate(client, season)
        body = _simulate(client, season, "end_of_regular_season").json()
        assert body["weeks_simulated"] == 15


class TestScheduleAndGames:
    def test_schedule_defaults_to_next_week(self, client: TestClient, season: Season,
                                            league: League):
        week = client.get(f"/api/leagues/{league.id}/schedule").json()
        assert week["week"] == 1
        assert len(week["games"]) == 16
        assert all(g["status"] == "scheduled" for g in week["games"])
        _simulate(client, season)
        assert client.get(f"/api/leagues/{league.id}/schedule").json()["week"] == 2
        played = client.get(f"/api/leagues/{league.id}/schedule?week=1").json()
        assert all(g["status"] == "final" for g in played["games"])

    def test_game_detail(self, client: TestClient, season: Season):
        game = _simulate(client, season).json()["franchise_games"][0]
        detail = client.get(f"/api/games/{game['id']}").json()
        assert detail["game"]["status"] == "final"
        assert sum(detail["line_score"]["home"]) == game["home_score"]
        assert sum(detail["line_score"]["away"]) == game["away_score"]
        assert detail["team_stats"]["home"]["points"] == game["home_score"]
        assert detail["plays"][0]["type"] == "kickoff"
        assert detail["plays"][-1]["home_score"] == game["home_score"]
        assert all(p["scoring"] for p in detail["scoring_plays"])
        passers = [p for p in detail["players"] if p["stats"].get("pass_att")]
        assert len(passers) >= 2 and all(p["name"] for p in passers)
        assert any(p["spot"] for p in detail["plays"])
        # Snaps name both calls; kickoffs and kicks don't.
        assert detail["plays"][0]["play_name"] is None
        named = [p for p in detail["plays"] if p["play_name"]]
        assert len(named) > 40 and all(p["defense_name"] for p in named if p["type"] == "run")

    def test_unplayed_game_detail_is_empty(self, client: TestClient, league: League):
        game = client.get(f"/api/leagues/{league.id}/schedule").json()["games"][0]
        detail = client.get(f"/api/games/{game['id']}").json()
        assert detail["plays"] == [] and detail["players"] == []
        assert detail["line_score"] == {"home": [], "away": []}

    def test_not_found(self, client: TestClient):
        assert client.get("/api/games/999999").status_code == 404
        assert client.post("/api/seasons/999999/simulate", json={}).status_code == 404


def test_league_with_played_games_can_be_deleted(client: TestClient, franchise: Franchise):
    spec = client.get("/api/leagues/template", params={
        "conferences": 1, "divisions": 2, "teams_per_division": 2}).json()
    created = client.post("/api/leagues", json={**spec, "seed": 3}).json()
    season_id = created["season"]["id"]
    client.post(f"/api/seasons/{season_id}/simulate", json={"until": "end_of_regular_season"})
    client.post(f"/api/franchises/{franchise.id}/activate")
    assert client.delete(f"/api/leagues/{created['league']['id']}").status_code == 204
