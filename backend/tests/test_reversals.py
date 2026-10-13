"""Milestone 13, part 4: reversing trades and rolling back a week
(docs/design/head-to-head-and-commissioner.md §4)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Award,
    DeadMoney,
    DraftPick,
    Franchise,
    Game,
    League,
    Notification,
    Player,
    PlayerGameStats,
    PlayoffSeed,
    Season,
    Team,
    Trade,
    User,
)
from app.schemas import SimulateRequest
from app.services import accounts, members
from app.services import season as season_service
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def manager(db: Session, owner: User, league: League,
            franchise: Franchise) -> TestClient:
    """A manager (not a commissioner) running another team, signed in."""
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id.desc()))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield sign_in_as(client, db, user)


def _contract(player: Player) -> tuple:
    c = player.active_contract
    return (c.team_id, c.salary, c.signing_bonus, c.start_year, c.years)


def _trade(client: TestClient, db: Session, league: League, picks: bool = False) -> dict:
    """An AI trade: our best player (and a pick) for their least valuable."""
    center = client.get(f"/api/leagues/{league.id}/trades").json()
    proposal = {"partner_id": center["partner"]["id"],
                "send_players": [center["mine"]["players"][0]["id"]],
                "receive_players": [center["theirs"]["players"][-1]["id"]]}
    if picks:
        proposal["send_picks"] = [center["mine"]["picks"][-1]["id"]]
    result = client.post(f"/api/leagues/{league.id}/trades", json=proposal).json()
    assert result["accepted"], result["evaluation"]
    return result["trade"]


class TestReversingTrades:
    def test_everything_goes_back_as_it_was(self, db: Session, client: TestClient,
                                            league: League, franchise: Franchise):
        center = client.get(f"/api/leagues/{league.id}/trades").json()
        ours = db.get(Player, center["mine"]["players"][0]["id"])
        theirs = db.get(Player, center["theirs"]["players"][-1]["id"])
        before = {p.id: (p.team_id, _contract(p)) for p in (ours, theirs)}
        dead = db.scalar(select(func.count(DeadMoney.id)))
        trade = _trade(client, db, league, picks=True)
        pick_id = trade["sent"][-1]["id"]
        assert db.scalar(select(func.count(DeadMoney.id))) > dead  # (the trade charged some)

        listed = client.get(f"/api/leagues/{league.id}/trades").json()["season_trades"]
        assert listed[0]["id"] == trade["id"] and listed[0]["problem"] is None
        reversed_ = client.post(f"/api/trades/{trade['id']}/reverse")
        assert reversed_.status_code == 200, reversed_.text
        assert reversed_.json()["reversed"] is True
        db.expire_all()
        for player in (db.get(Player, ours.id), db.get(Player, theirs.id)):
            assert (player.team_id, _contract(player)) == before[player.id]
            assert sum(c.is_active for c in player.contracts) == 1
        assert db.get(DraftPick, pick_id).team_id == franchise.team_id
        assert db.scalar(select(func.count(DeadMoney.id))) == dead
        center = client.get(f"/api/leagues/{league.id}/trades").json()
        assert center["history"][0]["reversed"] is True
        assert center["season_trades"][0]["problem"] == "It's already been reversed."
        entry = client.get(f"/api/leagues/{league.id}/log").json()["entries"][0]
        assert entry["action"] == "reverse" and ours.full_name in entry["summary"]
        assert db.scalar(select(Notification.title).where(
            Notification.key == f"reversed:{trade['id']}")) == "The commissioner reversed a trade"
        again = client.post(f"/api/trades/{trade['id']}/reverse")
        assert again.status_code == 409 and "already been reversed" in again.json()["detail"]

    def test_refused_once_someone_has_moved_on(self, db: Session, client: TestClient,
                                               league: League):
        trade = _trade(client, db, league)
        received = trade["received"][0]
        client.post(f"/api/players/{received['id']}/release")
        refused = client.post(f"/api/trades/{trade['id']}/reverse")
        assert refused.status_code == 409
        assert "is no longer with the team he was traded to" in refused.json()["detail"]
        assert db.get(Trade, trade["id"]).reversed_at is None

    def test_refused_after_a_new_contract(self, db: Session, client: TestClient,
                                          league: League):
        trade = _trade(client, db, league)
        client.put(f"/api/players/{trade['received'][0]['id']}/contract",
                   json={"salary": 2_000_000, "years": 2})
        refused = client.post(f"/api/trades/{trade['id']}/reverse")
        assert refused.status_code == 409 and "new contract" in refused.json()["detail"]

    def test_only_this_season_and_only_the_commissioner(self, db: Session, client: TestClient,
                                                        manager: TestClient, league: League,
                                                        season: Season):
        trade = _trade(client, db, league)
        assert manager.post(f"/api/trades/{trade['id']}/reverse").status_code == 403
        assert manager.get(f"/api/leagues/{league.id}/trades").json()["season_trades"] == []
        later = Season(league_id=league.id, year=season.year + 1, phase="free_agency")
        db.add(later)
        db.commit()
        refused = client.post(f"/api/trades/{trade['id']}/reverse")
        assert refused.status_code == 409 and "this season" in refused.json()["detail"]


def _injuries(db: Session, league: League) -> dict:
    return {p.id: (p.injury, p.injury_weeks, p.injury_status, p.injury_count or 0)
            for p in db.scalars(select(Player).where(Player.league_id == league.id))}


def _scores(db: Session, season: Season, **where) -> dict:
    query = select(Game).where(Game.season_id == season.id, Game.status == "final")
    for key, value in where.items():
        query = query.where(getattr(Game, key) == value)
    return {g.id: (g.home_score, g.away_score) for g in db.scalars(query)}


def _sim(db: Session, season: Season, until: str = "next_week") -> None:
    season_service.simulate(db, season, SimulateRequest(until=until))
    db.commit()


class TestRollingBack:
    def test_a_week_comes_undone_and_plays_the_same_again(
            self, db: Session, client: TestClient, league: League, season: Season):
        injuries = _injuries(db, league)
        assert client.get(f"/api/leagues/{league.id}/rollback").json() == {"label": None}
        assert client.post(f"/api/leagues/{league.id}/advance").status_code == 200
        played = _scores(db, season, week=1)
        assert played and db.scalar(select(func.count(PlayerGameStats.id)))
        assert _injuries(db, league) != injuries  # (a week of football hurts someone)
        assert db.scalar(select(Notification.id).where(Notification.kind == "game_result"))

        assert client.get(f"/api/leagues/{league.id}/rollback").json() == {"label": "Week 1"}
        rolled = client.post(f"/api/leagues/{league.id}/rollback")
        assert rolled.status_code == 200, rolled.text
        assert rolled.json() == {"label": "Week 1"}
        db.expire_all()
        assert _scores(db, season) == {}
        assert db.scalar(select(func.count(PlayerGameStats.id))) == 0
        assert (season.phase, season.current_week) == ("preseason", 1)
        assert _injuries(db, league) == injuries
        assert db.scalar(select(Notification.id).where(Notification.kind == "game_result")) is None
        entry = client.get(f"/api/leagues/{league.id}/log").json()["entries"][0]
        assert (entry["action"], entry["summary"]) == ("rollback", "Rolled back Week 1")

        # Only the last week, and only once.
        again = client.post(f"/api/leagues/{league.id}/rollback")
        assert again.status_code == 409 and "no week to roll back" in again.json()["detail"]
        _sim(db, season)
        assert _scores(db, season, week=1) == played

    def test_the_last_regular_week_takes_the_playoffs_with_it(
            self, db: Session, client: TestClient, league: League, season: Season):
        weeks = season_service.season_weeks(db, season.id)
        while season.phase != "playoffs":  # (week by week, as it's played again)
            _sim(db, season)
        seeds = {(s.team_id, s.seed) for s in db.scalars(select(PlayoffSeed))}
        assert season.phase == "playoffs" and seeds
        client.post(f"/api/leagues/{league.id}/rollback")
        db.expire_all()
        assert (season.phase, season.current_week) == ("regular_season", weeks)
        assert db.scalar(select(PlayoffSeed.id)) is None
        assert db.scalar(select(Game.id).where(Game.stage == "playoff")) is None
        _sim(db, season)
        assert {(s.team_id, s.seed) for s in db.scalars(select(PlayoffSeed))} == seeds

    def test_the_final_takes_the_champion_and_awards_with_it(
            self, db: Session, client: TestClient, league: League, season: Season):
        _sim(db, season, "end_of_regular_season")
        while season.phase == "playoffs":  # (a round at a time, as it's played again)
            _sim(db, season)
        champion = season.champion_team_id
        assert champion and db.scalar(select(Award.id).where(Award.season_id == season.id))
        final = _scores(db, season, stage="playoff", neutral_site=True)
        assert client.post(f"/api/leagues/{league.id}/rollback").status_code == 200
        db.expire_all()
        assert season.champion_team_id is None and season.phase == "playoffs"
        assert db.scalar(select(Award.id).where(Award.season_id == season.id)) is None
        assert _scores(db, season, stage="playoff", neutral_site=True) == {}
        _sim(db, season)
        assert season.champion_team_id == champion
        assert _scores(db, season, stage="playoff", neutral_site=True) == final

    def test_refused_while_a_game_is_coached_or_to_a_manager(
            self, db: Session, client: TestClient, manager: TestClient, league: League,
            season: Season):
        _sim(db, season)
        assert manager.post(f"/api/leagues/{league.id}/rollback").status_code == 403
        game = client.get("/api/franchise/next-game").json()["game"]
        client.post(f"/api/games/{game['id']}/coach")
        refused = client.post(f"/api/leagues/{league.id}/rollback")
        assert refused.status_code == 409 and "being coached" in refused.json()["detail"]
