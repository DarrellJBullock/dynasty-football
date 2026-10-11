import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.positions import Position
from app.models import Game, League, Season
from app.services.playback import replacement_position
from app.sim.calibration import default_league_teams
from app.sim.engine import SIM_VERSION, simulate_game
from app.sim.teams import SimTeam, replacement

SCRIMMAGE = {"run", "pass", "sack", "scramble", "kneel", "penalty"}

# ---------- the engine records who was on the field ----------


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


def test_every_scrimmage_play_records_its_22(teams):
    home, away = teams[2], teams[3]
    result = simulate_game(home, away, seed=8)
    rosters = {"home": set(home.players), "away": set(away.players)}
    abbreviations = {home.abbreviation: "home", away.abbreviation: "away"}
    for play in result.plays:
        if play.result["type"] not in SCRIMMAGE:
            assert play.personnel is None
            continue
        lineup = play.personnel
        assert len(lineup["offense"]) == len(lineup["defense"]) == 11
        assert len(set(lineup["offense"]) | set(lineup["defense"])) == 22
        offense = abbreviations[play.offense]
        defense = "away" if offense == "home" else "home"
        assert all(pid in rosters[offense] or pid < 0 for pid in lineup["offense"])
        assert all(pid in rosters[defense] or pid < 0 for pid in lineup["defense"])
        if play.defense:
            assert lineup["package"] == play.defense["package"]
        # Everyone the events name on a scrimmage play is in the lineup.
        named = {e.get(k) for e in play.events for k in ("player", "qb", "target", "to")
                 if e["t"] != "injury"} - {None}
        assert named <= set(lineup["offense"]) | set(lineup["defense"])


def test_kicks_name_a_returner(teams):
    home, away = teams[4], teams[5]
    result = simulate_game(home, away, seed=2)
    kicks = [(p, e) for p in result.plays for e in p.events if e["t"] in ("kickoff", "punt")]
    assert kicks
    for play, event in kicks:
        receiving = away if play.offense == home.abbreviation else home
        assert event["returner"] in receiving.players or event["returner"] < 0


def test_stand_in_ids_map_back_to_positions():
    for position in (Position.QB, Position.CB, Position.P):
        assert replacement_position(replacement(position, 2).id) == position


# ---------- the playback API ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def game(client: TestClient, db: Session, season: Season) -> Game:
    client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
    return db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1)).first()


def test_playback(client: TestClient, game: Game):
    body = client.get(f"/api/games/{game.id}/playback").json()
    assert body["sim_version"] == SIM_VERSION and body["approximate"] is False
    assert body["game"]["id"] == game.id
    assert [p["n"] for p in body["plays"]] == [p["n"] for p in game.play_log]
    players = {p["id"]: p for p in body["players"]}
    teams = {game.home_team.abbreviation: game.home_team_id,
             game.away_team.abbreviation: game.away_team_id}
    for play in body["plays"]:
        lineup = play["personnel"]
        if play["result"]["type"] in SCRIMMAGE:
            offense_team = teams[play["offense"]]
            assert all(players[pid]["team_id"] == offense_team for pid in lineup["offense"])
            assert all(players[pid]["team_id"] != offense_team for pid in lineup["defense"])
        for event in play["events"]:
            for key in ("player", "qb", "target", "kicker", "punter", "returner"):
                if event.get(key) is not None:
                    assert event[key] in players
            if event["t"] in ("kickoff", "punt"):
                assert "return" in event  # serialized with the engine's key
    sample = next(iter(players.values()))
    assert {"name", "short_name", "number", "position", "team_id", "speed", "height_in",
            "weight_lb"} <= set(sample)


def test_older_games_get_approximate_lineups(client: TestClient, db: Session, game: Game):
    log = copy.deepcopy(game.play_log)
    for play in log:
        play.pop("personnel", None)
        for event in play["events"]:
            event.pop("returner", None)
    game.play_log = log
    game.sim_version = "1.1"
    db.commit()
    body = client.get(f"/api/games/{game.id}/playback").json()
    assert body["approximate"] is True
    scrimmage = [p for p in body["plays"] if p["result"]["type"] in SCRIMMAGE]
    assert scrimmage and all(p["approximate"] and len(p["personnel"]["offense"]) == 11
                             and len(p["personnel"]["defense"]) == 11 for p in scrimmage)


def test_unplayed_and_missing_games(client: TestClient, db: Session, season: Season):
    unplayed = db.scalars(select(Game).where(Game.season_id == season.id,
                                             Game.status == "scheduled")).first()
    body = client.get(f"/api/games/{unplayed.id}/playback").json()
    assert body["plays"] == [] and body["players"] == []
    assert client.get("/api/games/999999/playback").status_code == 404
