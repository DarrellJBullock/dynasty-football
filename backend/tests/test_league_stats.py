from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Franchise, Game, League, PlayerGameStats, Season
from app.services.league_stats import CATEGORIES


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _sim(client: TestClient, season: Season, weeks: int = 2) -> None:
    for _ in range(weeks):
        client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})


def _season_sums(db: Session, season: Season) -> dict[int, dict[str, int]]:
    sums: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rows = db.scalars(select(PlayerGameStats).join(Game, Game.id == PlayerGameStats.game_id)
                      .where(Game.season_id == season.id))
    for row in rows:
        for column in ("pass_yds", "rush_yds", "rec_yds", "receptions", "sacks", "tackles",
                       "fg_made", "pass_td"):
            sums[row.player_id][column] += getattr(row, column)
        sums[row.player_id]["rush_long"] = max(sums[row.player_id]["rush_long"], row.rush_long)
    return sums


class TestLeaders:
    def test_empty_before_any_games(self, client: TestClient, league: League):
        body = client.get(f"/api/leagues/{league.id}/leaders").json()
        assert [c["key"] for c in body["categories"]] == list(CATEGORIES)
        assert all(c["leaders"] == [] for c in body["categories"])

    def test_leaders_match_the_box_scores(self, client: TestClient, db: Session,
                                          season: Season, league: League):
        _sim(client, season)
        sums = _season_sums(db, season)
        body = client.get(f"/api/leagues/{league.id}/leaders").json()
        for category in body["categories"]:
            stat = CATEGORIES[category["key"]].stat
            values = [row["value"] for row in category["leaders"]]
            assert values == sorted(values, reverse=True), category["key"]
            assert 0 < len(values) <= 5
            for row in category["leaders"]:
                if stat in sums[row["player_id"]]:
                    assert row["value"] == sums[row["player_id"]][stat]
                assert row["team"] is not None and 1 <= row["games"] <= 2
            best = max(v[stat] for v in sums.values() if stat in v) if stat in (
                "pass_yds", "rush_yds", "rec_yds", "receptions", "sacks", "tackles") else None
            if best is not None:
                assert values[0] == best

    def test_single_category_with_limit_and_max_columns(self, client: TestClient, db: Session,
                                                        season: Season, league: League):
        _sim(client, season)
        sums = _season_sums(db, season)
        body = client.get(f"/api/leagues/{league.id}/leaders",
                          params={"category": "rushing_yards", "limit": 20}).json()
        assert [c["key"] for c in body["categories"]] == ["rushing_yards"]
        rows = body["categories"][0]["leaders"]
        assert len(rows) == 20
        for row in rows:
            assert row["stats"]["rush_long"] == sums[row["player_id"]]["rush_long"]

    def test_unknown_category(self, client: TestClient, league: League):
        response = client.get(f"/api/leagues/{league.id}/leaders", params={"category": "dunks"})
        assert response.status_code == 422
        assert "passing_yards" in response.json()["detail"]

    def test_released_player_keeps_last_team(self, client: TestClient, season: Season,
                                             league: League, franchise: Franchise):
        _sim(client, season, 1)
        passing = client.get(f"/api/leagues/{league.id}/leaders",
                             params={"category": "passing_yards", "limit": 50}).json()
        ours = next(r for r in passing["categories"][0]["leaders"]
                    if r["team"]["id"] == franchise.team_id)
        client.post(f"/api/players/{ours['player_id']}/release")
        again = client.get(f"/api/leagues/{league.id}/leaders",
                           params={"category": "passing_yards", "limit": 50}).json()
        row = next(r for r in again["categories"][0]["leaders"]
                   if r["player_id"] == ours["player_id"])
        assert row["team"]["id"] == franchise.team_id


class TestPlayerStats:
    def test_totals_and_game_log(self, client: TestClient, season: Season,
                                 franchise: Franchise):
        _sim(client, season)
        qb = next(p for p in client.get(f"/api/teams/{franchise.team_id}/roster").json()
                  if p["position"] == "QB")
        body = client.get(f"/api/players/{qb['id']}/stats").json()
        assert body["games"] == 2
        assert [g["week"] for g in body["game_log"]] == [1, 2]
        assert body["totals"]["pass_yds"] == sum(g["stats"].get("pass_yds", 0)
                                                 for g in body["game_log"])
        for entry in body["game_log"]:
            game = client.get(f"/api/games/{entry['game_id']}").json()["game"]
            ours, theirs = ((game["home_score"], game["away_score"]) if entry["home"]
                            else (game["away_score"], game["home_score"]))
            assert entry["result"].split(" ")[1] == f"{ours}-{theirs}"
            assert entry["opponent"]["id"] != franchise.team_id

    def test_player_without_games(self, client: TestClient, league: League):
        free_agent = client.get(f"/api/leagues/{league.id}/free-agents").json()[0]
        body = client.get(f"/api/players/{free_agent['id']}/stats").json()
        assert body["games"] == 0 and body["game_log"] == [] and body["totals"] == {}
        assert body["team"] is None


class TestTeamStats:
    def test_team_totals_match_standings_and_opponents(self, client: TestClient,
                                                       season: Season, league: League):
        _sim(client, season)
        rows = client.get(f"/api/leagues/{league.id}/team-stats").json()
        assert len(rows) == 32
        standings = {r["team"]["id"]: r for d in client.get(
            f"/api/leagues/{league.id}/standings").json() for r in d["rows"]}
        for row in rows:
            record = standings[row["team"]["id"]]
            assert row["games"] == 2
            assert (row["wins"], row["losses"], row["ties"]) == (
                record["wins"], record["losses"], record["ties"])
            assert row["points_for"] == record["points_for"]
            assert row["points_against"] == record["points_against"]
        # League-wide, yards gained equal yards allowed and takeaways equal turnovers.
        assert sum(r["total_yds"] for r in rows) == sum(r["yds_allowed"] for r in rows)
        assert sum(r["turnovers"] for r in rows) == sum(r["takeaways"] for r in rows)
        assert sum(r["sacks_allowed"] for r in rows) == sum(r["sacks"] for r in rows)

    def test_before_any_games(self, client: TestClient, league: League):
        rows = client.get(f"/api/leagues/{league.id}/team-stats").json()
        assert all(r["games"] == 0 and r["points_for"] == 0 for r in rows)
