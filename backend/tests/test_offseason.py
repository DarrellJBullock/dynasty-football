import random
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.development import (
    contract_years,
    develop,
    overall_change,
    retirement_chance,
)
from app.domain.positions import ROSTER_MAX
from app.domain.ratings import ATTRIBUTES
from app.models import DepthChartEntry, Franchise, Game, League, Player, Season
from app.services.offseason import advance

# ---------- pure rules ----------


def _ratings(value: int = 70) -> dict[str, int]:
    return dict.fromkeys(ATTRIBUTES, value)


class TestDevelopment:
    def _mean_change(self, age: int, potential: int = 85, trait: str = "normal",
                     position: str = "WR") -> float:
        rng = random.Random(1)
        return sum(overall_change(rng, position, age, 70, potential, trait)
                   for _ in range(400)) / 400

    def test_young_players_grow_toward_potential(self):
        assert self._mean_change(23) > 2
        assert self._mean_change(23, potential=70) == 0  # already at potential
        assert self._mean_change(23, trait="elite") > self._mean_change(23, trait="normal")

    def test_prime_holds_and_veterans_decline(self):
        assert abs(self._mean_change(28)) < 1
        assert self._mean_change(31) < 0
        assert self._mean_change(34) < self._mean_change(31) - 2

    def test_kickers_age_slower(self):
        assert abs(self._mean_change(32, position="K")) < 1
        assert self._mean_change(32, position="WR") < -1

    def test_decline_hits_physical_attributes_hardest(self):
        rng = random.Random(3)
        totals = Counter()
        for _ in range(50):
            result = develop(rng, "MLB", 35, _ratings(), 70, "normal")
            for name in ("speed", "awareness"):
                totals[name] += result.ratings[name] - 70
        assert totals["speed"] < totals["awareness"] < 0

    def test_development_is_deterministic_and_keeps_potential_a_ceiling_floor(self):
        first = develop(random.Random(9), "QB", 22, _ratings(65), 80, "star")
        assert first == develop(random.Random(9), "QB", 22, _ratings(65), 80, "star")
        assert first.potential >= first.overall
        assert first.overall > 65

    def test_retirement_chances(self):
        assert retirement_chance("QB", 29, 70, signed=True) == 0
        assert retirement_chance("QB", 40, 90, signed=True) == 1
        assert retirement_chance("QB", 34, 85, True) < retirement_chance("QB", 34, 72, True) \
            < retirement_chance("QB", 34, 60, True)
        assert retirement_chance("QB", 33, 72, signed=False) > retirement_chance("QB", 33, 72, True)
        assert retirement_chance("K", 34, 72, True) < retirement_chance("WR", 34, 72, True)

    @pytest.mark.parametrize("age, low, high", [(23, 3, 5), (29, 2, 4), (33, 1, 2)])
    def test_contract_years_by_age(self, age, low, high):
        rng = random.Random(0)
        assert {contract_years(rng, age) for _ in range(50)} == set(range(low, high + 1))


# ---------- year rollover ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _finish(season: Season) -> Season:
    """Skip to the offseason without simulating games (the rollover doesn't need them)."""
    season.phase = "offseason"
    return season


def _players(db: Session, league: League) -> list[Player]:
    return list(db.scalars(select(Player).where(Player.league_id == league.id)
                           .options(selectinload(Player.contracts)).order_by(Player.id)))


class TestRollover:
    def test_requires_a_finished_season(self, client: TestClient, season: Season):
        response = client.post(f"/api/seasons/{season.id}/advance")
        assert response.status_code == 409
        assert "playoffs" in response.json()["detail"]

    def test_creates_the_next_season_with_a_schedule(
            self, client: TestClient, db: Session, season: Season, league: League):
        _finish(season)
        body = client.post(f"/api/seasons/{season.id}/advance").json()
        assert body["year"] == season.year + 1
        assert body["phase"] == "preseason" and body["current_week"] == 1
        assert body["weeks"] == 17 and body["champion"] is None
        games = db.scalars(select(Game).where(Game.season_id == body["id"])).all()
        per_team = Counter(t for g in games for t in (g.home_team_id, g.away_team_id))
        assert len(per_team) == 32 and set(per_team.values()) == {17}

        franchise = client.get("/api/franchise").json()
        assert franchise["season"]["id"] == body["id"]
        # The old season is complete and can't roll over twice; the new one isn't done yet.
        assert client.post(f"/api/seasons/{season.id}/advance").status_code == 409
        assert client.post(f"/api/seasons/{body['id']}/advance").status_code == 409

    def test_players_age_retire_and_rosters_refill(self, client: TestClient, db: Session,
                                                   season: Season, league: League):
        before = {p.id: (p.age, p.team_id) for p in _players(db, league)}
        new_season = advance(db, _finish(season))
        players = _players(db, league)
        log = new_season.offseason_log

        retired = [p for p in players if p.retired_year is not None]
        assert retired and {p.id for p in retired} == {e["player"] for e in log["retired"]}
        assert all(p.retired_year == season.year and p.team_id is None for p in retired)
        assert all(p.age == before[p.id][0] + 1 for p in players if p.id in before)

        rookies = [p for p in players if p.id not in before and p.team_id is not None]
        assert {p.id for p in rookies} == set(log["rookies"])
        assert all(p.years_pro == 0 and 21 <= p.age <= 23 for p in rookies)

        rosters = Counter(p.team_id for p in players if p.team_id is not None)
        assert set(rosters.values()) == {ROSTER_MAX}
        for player in players:
            if player.team_id is None:
                assert player.active_contract is None
            else:
                contract = player.active_contract
                assert sum(c.is_active for c in player.contracts) == 1
                assert contract.team_id == player.team_id
                assert contract.end_year >= new_season.year
                assert player.injury_status == "healthy"

        teams = client.get(f"/api/leagues/{league.id}/teams").json()
        assert all(t["cap_space"] >= 0 for t in teams)
        # Departed and retired players left the depth charts.
        gone = {e["player"] for k in ("retired", "departed") for e in log[k]}
        assert not db.scalars(select(DepthChartEntry).where(
            DepthChartEntry.player_id.in_(gone))).all()

    def test_retired_players_leave_free_agency(self, client: TestClient, db: Session,
                                               season: Season, league: League,
                                               franchise: Franchise):
        advance(db, _finish(season))
        retired = db.scalars(select(Player).where(Player.retired_year.is_not(None))).first()
        free_agents = client.get(f"/api/leagues/{league.id}/free-agents").json()
        assert retired.id not in {p["id"] for p in free_agents}
        assert len(free_agents) >= 64
        player = client.get(f"/api/players/{retired.id}").json()
        assert player["retired_year"] == season.year
        response = client.post(f"/api/teams/{franchise.team_id}/signings",
                               json={"player_id": retired.id, "years": 1})
        assert response.status_code == 409  # (its rollback also undoes the uncommitted rollover)

    def test_rollover_is_deterministic(self, db: Session, season: Season, league: League):
        existing = {p.id for p in _players(db, league)}

        def snapshot() -> list[tuple]:
            # New players' ids differ between runs on PostgreSQL (sequences don't roll back).
            return [(p.id if p.id in existing else "new", p.team_id, p.full_name, p.overall,
                     p.retired_year) for p in _players(db, league)]

        savepoint = db.begin_nested()
        advance(db, _finish(season))
        first = snapshot()
        savepoint.rollback()
        db.expire_all()
        advance(db, _finish(db.get(Season, season.id)))
        assert snapshot() == first

    def test_dashboard_recap_until_the_first_game(self, client: TestClient, db: Session,
                                                  season: Season, franchise: Franchise):
        new_season = advance(db, _finish(season))
        log = new_season.offseason_log
        recap = client.get("/api/franchise/dashboard").json()["offseason"]
        assert recap["from_year"] == season.year and recap["year"] == new_season.year
        mine = {e["player"] for e in log["re_signed"] if e["team"] == franchise.team_id}
        assert {r["player"]["id"] for r in recap["re_signed"]} == mine
        arrivals = {r["player"]["id"] for r in recap["signed"]} | {
            p["id"] for p in recap["rookies"]}
        assert len(arrivals) == len(recap["retired"]) + len(recap["departed"])
        assert all(r["after"] > r["before"] for r in recap["risers"])
        assert all(r["after"] < r["before"] for r in recap["decliners"])
        assert len(recap["league_retirements"]) == 5
        overalls = [r["player"]["overall"] for r in recap["league_retirements"]]
        assert overalls == sorted(overalls, reverse=True)

        client.post(f"/api/seasons/{new_season.id}/simulate", json={"until": "next_week"})
        assert client.get("/api/franchise/dashboard").json()["offseason"] is None


def test_full_season_then_next_year(client: TestClient, league: League, season: Season):
    """Play a whole season through the API, roll over, and play the new season's week 1."""
    sim = f"/api/seasons/{season.id}/simulate"
    client.post(sim, json={"until": "end_of_regular_season"})
    client.post(sim, json={"until": "end_of_playoffs"})
    new = client.post(f"/api/seasons/{season.id}/advance")
    assert new.status_code == 201
    new_id = new.json()["id"]

    standings = client.get(f"/api/leagues/{league.id}/standings").json()
    assert all(r["wins"] + r["losses"] + r["ties"] == 0 for d in standings for r in d["rows"])
    bracket = client.get(f"/api/leagues/{league.id}/playoffs").json()
    assert bracket["status"] == "projected" and bracket["season"]["id"] == new_id
    leaders = client.get(f"/api/leagues/{league.id}/leaders").json()
    assert all(c["leaders"] == [] for c in leaders["categories"])

    week1 = client.post(f"/api/seasons/{new_id}/simulate", json={"until": "next_week"}).json()
    assert week1["games_simulated"] == 16
    assert week1["season"]["phase"] == "regular_season"
    schedule = client.get(f"/api/leagues/{league.id}/schedule", params={"week": 1}).json()
    assert schedule["season"]["year"] == season.year + 1


def test_league_talent_is_stable_across_offseasons(client: TestClient, db: Session,
                                                    season: Season, league: League):
    """Retirements are balanced by development, signings, and rookies: over several years
    team strength, roster sizes, ages, and the cap stay in range."""
    def summary() -> tuple[float, float]:
        teams = client.get(f"/api/leagues/{league.id}/teams").json()
        assert all(t["roster_count"] == ROSTER_MAX and t["cap_space"] >= 0 for t in teams)
        rostered = [p for p in _players(db, league) if p.team_id is not None]
        return (sum(t["ratings"]["overall"] for t in teams) / len(teams),
                sum(p.age for p in rostered) / len(rostered))

    start_ovr, start_age = summary()
    for _ in range(4):
        season = advance(db, _finish(season))
        ovr, age = summary()
        assert abs(ovr - start_ovr) < 1.5
        assert abs(age - start_age) < 2
