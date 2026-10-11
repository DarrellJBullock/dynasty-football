import dataclasses
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Franchise, Game, League, Player, PlayerGameStats, Season
from app.services.injuries import after_week, status_for
from app.sim.calibration import default_league_teams
from app.sim.engine import simulate_game
from app.sim.injuries import (
    INJURY_TABLE,
    contact_ids,
    injury_chance,
    injury_details,
)
from app.sim.teams import SimPlayer, SimTeam
from app.sim.tuning import DEFAULT_TUNING
from tests.conftest import rollover

# ---------- engine ----------


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


def _player(toughness: int) -> SimPlayer:
    return SimPlayer(id=1, name="A. Player", position="RB", overall=75,
                     ratings={"toughness": toughness})


def test_contact_and_toughness_drive_the_chance():
    t = DEFAULT_TUNING
    assert injury_chance(_player(60), True, t) == pytest.approx(
        injury_chance(_player(60), False, t) * t.injury_contact_factor)
    assert injury_chance(_player(95), False, t) < injury_chance(_player(50), False, t)
    events = [{"t": "rush", "player": 5, "yards": 3}, {"t": "tackle", "by": [7, 8]},
              {"t": "pass", "qb": 2, "target": 9, "result": "incomplete"}]
    assert contact_ids(events) == {5, 7, 8}


def test_injury_details_follow_the_table():
    rng = random.Random(4)
    ranges = {name: span for name, _, span in INJURY_TABLE}
    seen = set()
    for _ in range(500):
        name, weeks = injury_details(rng)
        low, high = ranges[name]
        assert low <= weeks <= high
        seen.add(name)
    assert len(seen) == len(INJURY_TABLE)


def _injury_games(teams: list[SimTeam], count: int = 40):
    rng = random.Random(2)
    for seed in range(count):
        home, away = rng.sample(teams, 2)
        yield simulate_game(home, away, seed=seed)


def test_games_produce_injuries_and_the_injured_sit(teams):
    total = 0
    for result in _injury_games(teams):
        for i, play in enumerate(result.plays):
            for event in (e for e in play.events if e["t"] == "injury"):
                total += 1
                assert "is injured" in play.text
                later = [e for p in result.plays[i + 1:] for e in p.events]
                assert all(event["player"] not in _ids(e) for e in later)
    assert 1.0 <= total / 40 <= 5.0  # about 1.5 per team per game


PLAYER_KEYS = ("player", "qb", "target", "by", "to", "forced_by", "kicker", "punter")


def _ids(event: dict) -> set[int]:
    ids = set()
    for key in PLAYER_KEYS:
        value = event.get(key)
        ids.update(value if isinstance(value, list) else [value] if value else [])
    return ids


def test_injuries_do_not_change_plays_before_the_first_one(teams):
    """Injuries use their own random stream: a game plays out identically to an
    injury-free one until someone actually gets hurt."""
    home, away = teams[0], teams[1]
    seed = next(s for s in range(100) if simulate_game(home, away, seed=s).injuries)
    calm = simulate_game(home, away, seed=seed,
                         tuning=dataclasses.replace(DEFAULT_TUNING, injury_rate=0.0))
    real = simulate_game(home, away, seed=seed)
    assert not calm.injuries
    first = next(i for i, p in enumerate(real.plays) if any(e["t"] == "injury" for e in p.events))
    for a, b in zip(calm.plays[:first], real.plays[:first], strict=True):
        assert a.to_dict() == b.to_dict()
    assert simulate_game(home, away, seed=seed).injuries == real.injuries  # deterministic


# ---------- between weeks ----------


@pytest.mark.parametrize("weeks, status", [(0, "questionable"), (1, "out"), (3, "out"),
                                           (4, "injured_reserve"), (99, "injured_reserve")])
def test_status_for(weeks, status):
    assert status_for(weeks) == status


def _hurt(player: Player, injury: str, weeks: int) -> None:
    player.injury, player.injury_weeks, player.injury_status = injury, weeks, status_for(weeks)


def test_recovery_counts_down_one_game_per_week(db: Session, league: League):
    a, b, c, manual = db.scalars(select(Player).where(Player.team_id.is_not(None))
                                 .order_by(Player.id).limit(4)).all()
    _hurt(a, "Ankle sprain", 0)
    _hurt(b, "Knee sprain", 2)
    _hurt(c, "Torn ACL", 99)
    manual.injury_status = "out"  # set by hand: left alone

    after_week(db, league.id, [])
    assert (a.injury_status, b.injury_status, b.injury_weeks) == ("healthy", "out", 1)
    assert a.injury is None and c.injury_status == "injured_reserve"
    after_week(db, league.id, [])
    assert b.injury_status == "healthy" and b.injury is None
    assert manual.injury_status == "out"
    assert c.injury_weeks == 99  # season-ending: no countdown


def _sim(client: TestClient, season: Season, until: str = "next_week"):
    return client.post(f"/api/seasons/{season.id}/simulate", json={"until": until}).json()


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _week_injuries(db: Session, season: Season, week: int) -> list[dict]:
    games = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == week))
    return [e for g in games for p in g.play_log for e in p["events"] if e["t"] == "injury"]


def test_simulated_injuries_update_players_and_lineups(client: TestClient, db: Session,
                                                       season: Season):
    _sim(client, season)
    events = _week_injuries(db, season, 1)
    assert events
    for event in events:
        player = db.get(Player, event["player"])
        assert player.injury == event["injury"]
        assert player.injury_weeks == event["weeks"]
        assert player.injury_status == status_for(event["weeks"])

    _sim(client, season)
    out = [e["player"] for e in events if e["weeks"] >= 1]
    week2 = db.scalars(select(PlayerGameStats.player_id).join(Game).where(
        Game.season_id == season.id, Game.week == 2)).all()
    assert out and not set(out) & set(week2)
    for event in events:
        player = db.get(Player, event["player"])
        if event["weeks"] <= 1 and player.id not in {e["player"] for e in
                                                     _week_injuries(db, season, 2)}:
            assert player.injury_status == "healthy"


def test_injury_report_and_game_page(client: TestClient, db: Session, season: Season,
                                     franchise: Franchise):
    _sim(client, season, "end_of_regular_season")
    dashboard = client.get("/api/franchise/dashboard").json()
    hurt = db.scalars(select(Player).where(Player.team_id == franchise.team_id,
                                           Player.injury_status != "healthy")).all()
    report = dashboard["injury_report"]
    assert {p["id"] for p in report} == {p.id for p in hurt}
    assert [p["injury_weeks"] for p in report] == sorted(
        (p["injury_weeks"] for p in report), reverse=True)

    game = next(g for g in db.scalars(select(Game).where(Game.season_id == season.id))
                if any(e["t"] == "injury" for p in g.play_log for e in p["events"]))
    detail = client.get(f"/api/games/{game.id}").json()
    assert detail["injuries"]
    for row in detail["injuries"]:
        assert row["team_id"] in (game.home_team_id, game.away_team_id)
        assert db.get(Player, row["player_id"]).full_name == row["name"]


def test_marking_a_player_healthy_clears_the_injury(client: TestClient, db: Session):
    player = db.scalars(select(Player).where(Player.team_id.is_not(None))).first()
    _hurt(player, "Hand fracture", 3)
    body = client.patch(f"/api/players/{player.id}", json={"injury_status": "healthy"}).json()
    assert body["injury"] is None and body["injury_weeks"] == 0


def test_the_offseason_heals_everyone(db: Session, season: Season, league: League):
    player = db.scalars(select(Player).where(Player.team_id.is_not(None))).first()
    _hurt(player, "Torn ACL", 99)
    season.phase = "offseason"
    rollover(db, season)
    assert db.scalar(select(Player).where(Player.league_id == league.id,
                                          Player.injury.is_not(None))) is None
