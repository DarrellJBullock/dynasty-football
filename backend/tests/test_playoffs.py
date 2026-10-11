import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.playoffs import (
    Ranker,
    Result,
    TeamInfo,
    pair_round,
    round_names,
    seed_conference,
    seeds_per_conference,
)
from app.models import Franchise, Game, League, PlayerGameStats, PlayoffSeed, Season

# ---------- pure rules ----------


class TestBracketRules:
    @pytest.mark.parametrize("teams, seeds", [(16, 7), (12, 6), (8, 4), (6, 2), (4, 2), (2, 2)])
    def test_seeds_per_conference(self, teams, seeds):
        assert seeds_per_conference(teams) == seeds

    @pytest.mark.parametrize("alive, byes, games", [
        ([1, 2, 3, 4, 5, 6, 7], [1], [(2, 7), (3, 6), (4, 5)]),
        ([1, 2, 3, 4, 5, 6], [1, 2], [(3, 6), (4, 5)]),
        ([1, 2, 3, 4], [], [(1, 4), (2, 3)]),
        ([1, 3, 5, 7], [], [(1, 7), (3, 5)]),  # reseeded: top seed hosts the lowest left
        ([2, 6], [], [(2, 6)]),
    ])
    def test_pair_round(self, alive, byes, games):
        assert pair_round(alive) == (byes, games)

    def test_round_names(self):
        assert round_names(7, 2) == ["Wild Card", "Divisional", "Conference Championship",
                                     "Championship"]
        assert round_names(4, 1) == ["Semifinal", "Championship"]
        assert round_names(2, 1) == ["Championship"]


def _teams(*specs) -> list[TeamInfo]:
    return [TeamInfo(id=i, division=d, conference=c) for i, d, c in specs]


def win(winner: int, loser: int, margin: int = 7) -> Result:
    return Result(home=winner, away=loser, home_score=20 + margin, away_score=20)


class TestTiebreakers:
    def test_win_percentage_first(self):
        teams = _teams((1, 1, 1), (2, 1, 1), (3, 1, 1))
        ranker = Ranker(teams, [win(2, 1), win(2, 3), win(1, 3)], salt="x")
        assert ranker.rank([1, 2, 3]) == [2, 1, 3]

    def test_head_to_head_breaks_a_tie(self):
        teams = _teams((1, 1, 1), (2, 2, 1), (3, 3, 1), (4, 4, 1))
        # 1 and 2 are both 1-1, but 2 beat 1.
        results = [win(2, 1), win(1, 3), win(4, 2)]
        assert Ranker(teams, results, salt="x").rank([1, 2]) == [2, 1]

    def test_division_record_then_point_differential(self):
        teams = _teams((1, 1, 1), (2, 1, 1), (3, 1, 1), (4, 2, 1), (5, 2, 1))
        # 1 and 2 both 1-1 and never met; 1 won its division game, 2 lost its.
        results = [win(1, 3), win(4, 1), win(3, 2), win(2, 5)]
        assert Ranker(teams, results, salt="x").rank([1, 2]) == [1, 2]
        # Identical records everywhere → point differential decides.
        teams = _teams((1, 1, 1), (2, 2, 1), (3, 3, 1), (4, 4, 1))
        results = [win(1, 3, margin=21), win(2, 4, margin=3)]
        assert Ranker(teams, results, salt="x").rank([1, 2]) == [1, 2]

    def test_coin_flip_is_deterministic_per_season(self):
        teams = _teams((1, 1, 1), (2, 2, 1))
        first = Ranker(teams, [], salt="season:1").rank([1, 2])
        assert Ranker(teams, [], salt="season:1").rank([1, 2]) == first
        assert {tuple(Ranker(teams, [], salt=f"season:{i}").rank([1, 2]))
                for i in range(20)} == {(1, 2), (2, 1)}

    def test_division_winners_take_the_top_seeds(self):
        # Two divisions of four; division 2's winner is 2-4 overall but still seeds above
        # division 1's 4-2 runner-up.
        teams = _teams(*[(i, 1 if i <= 4 else 2, 1) for i in range(1, 9)])
        results = [win(1, 2), win(1, 3), win(1, 4), win(2, 3), win(2, 4), win(2, 6),
                   win(2, 7), win(5, 6), win(5, 8), win(3, 5), win(4, 5), win(1, 5),
                   win(3, 4)]  # 3 (2-2) clearly ahead of 4 (1-3)
        seeds = seed_conference(Ranker(teams, results, salt="x"), 1)
        assert [s.team_id for s in seeds] == [1, 5, 2, 3]
        assert [s.division_winner for s in seeds] == [True, True, False, False]


# ---------- season flow ----------

def _sim(client: TestClient, season: Season, until: str):
    return client.post(f"/api/seasons/{season.id}/simulate", json={"until": until})


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _playoff_games(db: Session, season: Season) -> list[Game]:
    return db.scalars(select(Game).where(Game.season_id == season.id, Game.stage == "playoff")
                      .order_by(Game.playoff_round, Game.id)).all()


class TestPlayoffFlow:
    def test_regular_season_end_seeds_and_schedules_wild_card(
            self, client: TestClient, db: Session, season: Season, league: League):
        body = _sim(client, season, "end_of_regular_season").json()
        assert body["season"]["phase"] == "playoffs"
        assert body["season"]["next_round"] == "Wild Card"
        seeds = db.scalars(select(PlayoffSeed).where(PlayoffSeed.season_id == season.id)).all()
        assert len(seeds) == 14
        games = _playoff_games(db, season)
        assert len(games) == 6 and all(g.playoff_round == 1 for g in games)
        by_team = {s.team_id: s.seed for s in seeds}
        assert sorted((by_team[g.home_team_id], by_team[g.away_team_id]) for g in games) == \
            [(2, 7), (2, 7), (3, 6), (3, 6), (4, 5), (4, 5)]
        assert all(g.week == 18 for g in games)

        bracket = client.get(f"/api/leagues/{league.id}/playoffs").json()
        assert bracket["status"] == "in_progress"
        assert [r["name"] for r in bracket["rounds"]] == [
            "Wild Card", "Divisional", "Conference Championship", "Championship"]
        assert all(len(c["seeds"]) == 7 for c in bracket["conferences"])
        for conference in bracket["conferences"]:
            assert [s["division_winner"] for s in conference["seeds"]] == [True] * 4 + [False] * 3

    def test_rounds_reseed_and_crown_a_champion(self, client: TestClient, db: Session,
                                                season: Season, league: League):
        _sim(client, season, "end_of_regular_season")
        seeds = {s.team_id: s.seed for s in db.scalars(
            select(PlayoffSeed).where(PlayoffSeed.season_id == season.id))}

        divisional = _sim(client, season, "next_week").json()
        assert divisional["games_simulated"] == 6
        assert divisional["season"]["next_round"] == "Divisional"
        round2 = [g for g in _playoff_games(db, season) if g.playoff_round == 2]
        assert len(round2) == 4
        for game in round2:
            assert seeds[game.home_team_id] < seeds[game.away_team_id]  # higher seed hosts
        assert {seeds[g.home_team_id] for g in round2} >= {1}  # the bye team plays now

        final = _sim(client, season, "end_of_playoffs").json()
        assert final["season"]["phase"] == "offseason"
        champion = final["season"]["champion"]
        assert champion is not None
        games = _playoff_games(db, season)
        assert [g.playoff_round for g in games].count(4) == 1
        championship = games[-1]
        assert championship.neutral_site is True
        winner = (championship.home_team_id if championship.home_score > championship.away_score
                  else championship.away_team_id)
        assert winner == champion["id"]
        assert all(g.status == "final" and g.home_score != g.away_score for g in games)

        assert _sim(client, season, "next_week").status_code == 409
        bracket = client.get(f"/api/leagues/{league.id}/playoffs").json()
        assert bracket["status"] == "complete"
        assert bracket["champion"]["id"] == champion["id"]
        assert sum(1 for c in bracket["conferences"] for s in c["seeds"] if s["eliminated"]) == 13

    def test_cannot_sim_playoffs_early(self, client: TestClient, season: Season):
        response = _sim(client, season, "end_of_playoffs")
        assert response.status_code == 409
        assert "regular season" in response.json()["detail"]

    def test_playoff_games_do_not_count_toward_records_or_stats(
            self, client: TestClient, db: Session, season: Season, league: League):
        _sim(client, season, "end_of_regular_season")
        before = client.get(f"/api/leagues/{league.id}/leaders",
                            params={"category": "passing_yards", "limit": 50}).json()
        _sim(client, season, "end_of_playoffs")
        standings = client.get(f"/api/leagues/{league.id}/standings").json()
        assert all(r["wins"] + r["losses"] + r["ties"] == 17 for d in standings for r in d["rows"])
        after = client.get(f"/api/leagues/{league.id}/leaders",
                           params={"category": "passing_yards", "limit": 50}).json()
        assert after["categories"] == before["categories"]
        # Playoff box scores are still stored and shown on game pages.
        game = _playoff_games(db, season)[0]
        assert db.scalars(select(PlayerGameStats).where(PlayerGameStats.game_id == game.id)).all()
        detail = client.get(f"/api/games/{game.id}").json()
        assert detail["game"]["round_name"] == "Wild Card"
        assert detail["game"]["stage"] == "playoff"

    def test_projected_picture_during_the_season(self, client: TestClient, season: Season,
                                                 league: League):
        client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
        bracket = client.get(f"/api/leagues/{league.id}/playoffs").json()
        assert bracket["status"] == "projected"
        assert all(len(c["seeds"]) == 7 for c in bracket["conferences"])
        assert all(r["games"] == [] for r in bracket["rounds"])
        assert bracket["champion"] is None


def test_small_single_conference_league(client: TestClient, franchise: Franchise):
    spec = client.get("/api/leagues/template", params={
        "conferences": 1, "divisions": 2, "teams_per_division": 2}).json()
    created = client.post("/api/leagues", json={**spec, "seed": 5}).json()
    season_id = created["season"]["id"]
    body = client.post(f"/api/seasons/{season_id}/simulate",
                       json={"until": "end_of_regular_season"}).json()
    assert body["season"]["next_round"] == "Championship"
    bracket = client.get(f"/api/leagues/{created['league']['id']}/playoffs").json()
    assert [len(c["seeds"]) for c in bracket["conferences"]] == [2]
    assert [r["name"] for r in bracket["rounds"]] == ["Championship"]

    final = client.post(f"/api/seasons/{season_id}/simulate", json={"until": "next_week"}).json()
    assert final["games_simulated"] == 1
    assert final["season"]["phase"] == "offseason"
    assert final["season"]["champion"] is not None

    client.post(f"/api/franchises/{franchise.id}/activate")
    assert client.delete(f"/api/leagues/{created['league']['id']}").status_code == 204
