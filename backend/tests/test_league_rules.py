"""Milestone 13, part 5: league rules (docs/design/head-to-head-and-commissioner.md §4)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Franchise,
    Game,
    League,
    Notification,
    Player,
    PlayoffSeed,
    Season,
    Team,
    User,
)
from app.schemas import SimulateRequest
from app.services import accounts, members, offseason, playoffs
from app.services import season as season_service
from tests.conftest import make_client, rollover, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def manager(db: Session, owner: User, league: League,
            franchise: Franchise) -> tuple[User, TestClient]:
    """A manager (not a commissioner) running another team, signed in."""
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id.desc()))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user)


def _url(league: League) -> str:
    return f"/api/leagues/{league.id}/rules"


def _roster(db: Session, team_id: int) -> int:
    return db.scalar(select(func.count(Player.id)).where(Player.team_id == team_id))


def _weeks(db: Session, season: Season) -> int:
    return db.scalar(select(func.max(Game.week)).where(Game.season_id == season.id,
                                                       Game.stage == "regular"))


class TestTheRules:
    def test_as_they_are(self, client: TestClient, league: League, season: Season):
        rules = client.get(_url(league)).json()
        assert rules["roster_max"] == 53 and rules["salary_cap"] == league.salary_cap
        assert rules["cap_growth_pct"] == 0 and rules["playoff_seeds"] is None
        assert (rules["seeds"], rules["byes"]) == (7, 1)  # (16-team conferences)
        assert rules["seed_choices"] == [2, 3, 4, 5, 6, 7, 8]
        assert rules["season_weeks"] == 17 and rules["locked_reason"] is None

    def test_only_between_seasons(self, db: Session, client: TestClient, league: League,
                                  season: Season):
        season_service.simulate(db, season, SimulateRequest(until="next_week"))
        db.commit()
        rules = client.get(_url(league)).json()
        assert "between seasons" in rules["locked_reason"]
        refused = client.patch(_url(league), json={"roster_max": 50})
        assert refused.status_code == 409 and "between seasons" in refused.json()["detail"]

    def test_the_commissioners_and_logged_for_everyone(self, db: Session, client: TestClient,
                                                       manager, league: League):
        user, other = manager
        assert other.patch(_url(league), json={"roster_max": 50}).status_code == 403
        assert other.get(_url(league)).status_code == 200
        changed = client.patch(_url(league), json={"cap_growth_pct": 3.5, "salary_cap":
                                                   300_000_000})
        assert changed.status_code == 200, changed.text
        assert changed.json()["cap_growth_pct"] == 3.5
        entry = other.get(f"/api/leagues/{league.id}/log").json()["entries"][0]
        assert entry["action"] == "rules"
        assert {c["field"]: c["after"] for c in entry["changes"]} == {
            "salary_cap": 300_000_000, "cap_growth_bp": 350}
        assert db.scalar(select(Notification.title).where(
            Notification.user_id == user.id, Notification.kind == "rules"))

    def test_out_of_range(self, client: TestClient, league: League):
        for body in ({"roster_max": 44}, {"roster_max": 61}, {"playoff_seeds": 9},
                     {"season_weeks": 0}, {"season_weeks": 21}, {"cap_growth_pct": 11},
                     {"salary_cap": 1}):
            assert client.patch(_url(league), json=body).status_code == 422, body


class TestRosterSize:
    def test_a_smaller_roster_cuts_ai_teams_now_and_members_before_week_1(
            self, db: Session, client: TestClient, league: League, franchise: Franchise,
            season: Season):
        assert season.phase == "preseason"
        assert client.patch(_url(league), json={"roster_max": 50}).status_code == 200
        ai = db.scalar(select(Team.id).where(Team.league_id == league.id,
                                             Team.id != franchise.team_id))
        assert _roster(db, ai) == 50
        assert _roster(db, franchise.team_id) == 53  # (the member cuts their own)
        refused = client.post(f"/api/seasons/{season.id}/simulate", json={"until": "next_week"})
        assert refused.status_code == 409 and "must cut to 50" in refused.json()["detail"]
        alerts = client.get("/api/franchise/dashboard").json()["alerts"]
        assert any("Cut your roster to 50" in a["message"] for a in alerts)

    def test_a_bigger_roster_has_room(self, db: Session, client: TestClient, league: League,
                                      franchise: Franchise):
        team = f"/api/teams/{franchise.team_id}"
        new = {"first_name": "Ari", "last_name": "Vance", "position": "QB", "jersey_number": 93}
        assert client.post(f"{team}/players", json=new).status_code == 409  # (53 of 53)
        client.patch(_url(league), json={"roster_max": 55})
        assert client.post(f"{team}/players", json=new).status_code == 201
        assert client.get(team).json()["roster_max"] == 55


class TestTheCap:
    def test_it_grows_each_offseason(self, db: Session, client: TestClient, league: League,
                                     season: Season):
        client.patch(_url(league), json={"salary_cap": 200_000_000, "cap_growth_pct": 5})
        season.phase = "offseason"
        offseason.advance(db, season)
        assert league.salary_cap == 210_000_000

    def test_none_by_default(self, db: Session, league: League, season: Season):
        cap = league.salary_cap
        season.phase = "offseason"
        offseason.advance(db, season)
        assert league.salary_cap == cap


class TestThePlayoffs:
    def test_fewer_seeds_and_rounds(self, db: Session, client: TestClient, league: League,
                                    season: Season):
        body = client.patch(_url(league), json={"playoff_seeds": 4}).json()
        assert (body["seeds"], body["byes"]) == (4, 0)
        season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"))
        counts = db.execute(select(func.count(PlayoffSeed.id)).where(
            PlayoffSeed.season_id == season.id).group_by(PlayoffSeed.conference_id)).scalars()
        assert set(counts) == {4}
        assert playoffs.round_count(db, season) == 3  # (semifinal, conference final, final)
        assert playoffs.round_name(db, season, 1) == "Semifinal"

    def test_back_to_automatic(self, client: TestClient, league: League):
        client.patch(_url(league), json={"playoff_seeds": 6})
        body = client.patch(_url(league), json={"playoff_seeds": None}).json()
        assert body["playoff_seeds"] is None and body["seeds"] == 7


class TestSeasonLength:
    def test_before_week_1_the_schedule_is_drawn_again(self, db: Session, client: TestClient,
                                                        league: League, season: Season,
                                                        franchise: Franchise):
        assert client.patch(_url(league), json={"season_weeks": 10}).json()["season_weeks"] == 10
        assert _weeks(db, season) == 10
        games = db.scalar(select(func.count(Game.id)).where(
            Game.season_id == season.id,
            (Game.home_team_id == franchise.team_id) | (Game.away_team_id == franchise.team_id)))
        assert games == 10
        assert client.get("/api/franchise").json()["season"]["weeks"] == 10

    def test_in_the_offseason_it_is_the_next_schedule(self, db: Session, client: TestClient,
                                                      league: League, season: Season):
        season.phase = "offseason"
        db.commit()
        client.patch(_url(league), json={"season_weeks": 12})
        assert _weeks(db, season) == 17  # (this season's stands)
        new = rollover(db, season)
        assert _weeks(db, new) == 12
