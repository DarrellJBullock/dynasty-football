"""Milestone 14, part 1: owners and fans (docs/design/owners-and-front-offices.md §3)."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import owners as rules
from app.models import Franchise, League, Owner, OwnerSeason, Season, Team
from app.schemas import SimulateRequest
from app.services import owners
from app.services import season as season_service
from tests.conftest import rollover


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _season(**kw) -> rules.Season:
    base = {"wins": 0, "losses": 0, "ties": 0, "weeks": 17}
    return rules.Season(**{**base, **kw})


class TestTheRules:
    def test_markets_are_a_quarter_small_half_medium_a_quarter_large(self):
        spread = rules.markets(random.Random(1), 32)
        assert (spread.count("small"), spread.count("medium"), spread.count("large")) == (8, 16, 8)

    def test_where_a_roster_stands(self):
        assert [rules.situation(r, 30) for r in (1, 10, 11, 20, 21, 30)] == [
            "contender", "contender", "middle", "middle", "rebuilding", "rebuilding"]

    def test_goals_come_from_the_owner_and_the_roster(self):
        kinds = [g.kind for g in rules.goals("win_now", "contender", 17)]
        assert kinds == ["title", "wins", "playoffs"]
        assert rules.goals("win_now", "contender", 17)[1].target == 11  # (.65 of 17)
        assert [g.kind for g in rules.goals("build", "rebuilding", 17)] == ["young", "wins"]
        assert rules.goals("build", "rebuilding", 17)[1].target == 6
        assert [g.kind for g in rules.goals("profit", "middle", 10)] == ["fans", "wins"]
        assert rules.goals("win_now", "contender", 17)[0].label == "Win the championship"
        assert rules.goals("build", "middle", 17)[0].label == "Start 6 players aged 25 or younger"

    def test_fans_follow_the_season(self):
        unbeaten = _season(wins=17, playoffs=True, playoff_wins=4, title=True, stars=7)
        parts = dict(rules.fan_change(unbeaten))
        assert parts == {"Record": 20, "Made the playoffs": 5, "Playoff wins": 12,
                         "Champions": 10, "5 star players": 5}
        assert rules.fan_mood(50, unbeaten) == 100
        # Halfway through a 4-4 season, nothing has moved; a 0-8 start has.
        assert rules.fan_mood(50, _season(wins=4, losses=4)) == 50
        assert rules.fan_mood(50, _season(losses=8)) == 41  # (−20 × 8/17)
        # Between seasons the mood drifts a quarter of the way back to 50.
        assert rules.fan_mood(90, _season(wins=8, losses=8, ties=1), drift=True) == 80

    def test_goals_met_missed_or_still_open(self):
        nine = rules.Goal("wins", 9, 6)
        assert rules.met(nine, _season(wins=9, losses=2), 50, final=False) is True
        assert rules.met(nine, _season(wins=2, losses=9), 50, final=False) is False
        assert rules.met(nine, _season(wins=5, losses=5), 50, final=False) is None
        assert rules.on_track(nine, _season(wins=5, losses=3), 50)
        assert not rules.on_track(nine, _season(wins=3, losses=5), 50)
        playoffs = rules.Goal("playoffs", 1, 10)
        assert rules.met(playoffs, _season(wins=12, losses=5), 50, final=False) is None
        assert rules.met(playoffs, _season(wins=12, losses=5), 50, final=True) is False
        assert rules.met(playoffs, _season(wins=12, losses=5, playoffs=True), 50, final=True)

    def test_a_patient_owner_forgives_more(self):
        missed = [(rules.Goal("title", 1, 10), False), (rules.Goal("wins", 11, 6), True)]
        impatient = dict(rules.confidence_change(missed, 1, 50))
        patient = dict(rules.confidence_change(missed, 5, 50))
        assert impatient["Win the championship"] == -13 and patient["Win the championship"] == -5
        assert impatient["Win 11 games"] == 6 and impatient["Fan mood"] == 0
        assert dict(rules.confidence_change([], 3, 90))["Fan mood"] == 8

    def test_the_owners_word(self):
        assert rules.verdict(20, 80) == "is delighted"
        assert rules.verdict(0, 60) == "is satisfied"
        assert rules.verdict(-20, 40) == "is angry"
        assert rules.verdict(10, 25) == "is losing patience"


class TestOwners:
    def test_every_team_gets_one_once(self, db: Session, league: League, season: Season):
        owners.ensure_owners(db, league)
        owners.ensure_owners(db, league)
        teams = db.scalar(select(func.count(Team.id)).where(Team.league_id == league.id))
        assert db.scalar(select(func.count(Owner.id))) == teams
        rows = db.scalars(select(Owner).order_by(Owner.team_id)).all()
        assert {o.priority for o in rows} <= set(rules.PRIORITIES)
        assert all(1 <= o.patience <= 5 and o.confidence == 60 for o in rows)
        markets = [t.market for t in db.scalars(select(Team).where(Team.league_id == league.id))]
        assert markets.count("large") == markets.count("small") == teams // 4
        # The same league always gets the same owners (their own random stream).
        rng = random.Random(f"owners:{league.id}")
        rules.markets(rng, teams)
        assert (rows[0].priority, rows[0].patience) == tuple(vars(rules.make(rng)).values())

    def test_goals_are_set_for_the_season_from_the_roster(self, db: Session, league: League,
                                                          season: Season):
        assert season.phase == "preseason"
        owners.ensure_owners(db, league)
        rows = db.scalars(select(OwnerSeason).where(OwnerSeason.season_id == season.id)).all()
        assert len(rows) == len(league.teams)
        places = [r.situation for r in rows]
        assert places.count("contender") == places.count("rebuilding") == round(len(rows) / 3)
        assert all(2 <= len(r.goals) <= 3 for r in rows)

    def test_a_new_league_has_them_at_once(self, db: Session, client: TestClient):
        spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
        made = client.post("/api/leagues", json=spec.json())
        assert made.status_code == 201, made.text
        league_id = made.json()["league"]["id"]
        assert db.scalar(select(func.count(Owner.id)).where(Owner.league_id == league_id)) == 4


def _sim(db: Session, season: Season, until: str) -> None:
    season_service.simulate(db, season, SimulateRequest(until=until))
    db.commit()


class TestTheSeason:
    def test_the_owner_card_follows_the_season(self, db: Session, client: TestClient,
                                               franchise: Franchise, season: Season):
        url = f"/api/teams/{franchise.team_id}/owner"
        before = client.get(url).json()
        assert before["confidence"] == 60 and before["last_review"] is None
        assert before["situation"] in rules.SITUATIONS and before["goals"]
        assert {g["status"] for g in before["goals"]} <= {"on_track", "behind"}
        assert before["fan_mood"] == rules.START_FAN_MOOD[before["market"]]
        _sim(db, season, "end_of_regular_season")
        during = client.get(url).json()
        assert "Record" in dict(during["fan_parts"])
        assert during["fan_mood"] == rules.clamp(before["fan_mood"] + sum(
            v for _, v in during["fan_parts"]))
        wins = next(g for g in during["goals"] if g["kind"] == "wins")
        assert wins["status"] in ("met", "missed")  # (the regular season is over)

    def test_the_owner_reviews_the_season_and_a_rollback_takes_it_back(
            self, db: Session, client: TestClient, franchise: Franchise, league: League,
            season: Season):
        _sim(db, season, "end_of_regular_season")
        while season.phase == "playoffs":
            _sim(db, season, "next_week")
        url = f"/api/teams/{franchise.team_id}/owner"
        card = client.get(url).json()
        review = card["last_review"]
        assert review["year"] == season.year and review["verdict"]
        assert review["confidence_after"] == rules.clamp(
            review["confidence_before"] + sum(v for _, v in review["confidence_parts"]))
        assert card["confidence"] == review["confidence_after"]
        assert card["fan_mood"] == review["fan_mood_after"]
        assert [r["met"] for r in review["results"]] == [
            g["status"] == "met" for g in card["goals"]]
        # Every owner reviewed theirs.
        assert db.scalar(select(func.count(OwnerSeason.id)).where(
            OwnerSeason.season_id == season.id, OwnerSeason.results.is_(None))) == 0

        assert client.post(f"/api/leagues/{league.id}/rollback").status_code == 200
        back = client.get(url).json()
        assert back["last_review"] is None and back["confidence"] == 60
        _sim(db, season, "next_week")
        assert client.get(url).json()["last_review"] == review  # (the same final, the same review)

    def test_next_season_brings_new_goals(self, db: Session, client: TestClient,
                                          franchise: Franchise, season: Season):
        _sim(db, season, "end_of_regular_season")
        _sim(db, season, "end_of_playoffs")
        new = rollover(db, season)
        db.commit()
        assert new.phase == "preseason"
        assert db.scalar(select(func.count(OwnerSeason.id)).where(
            OwnerSeason.season_id == new.id)) == db.scalar(select(func.count(Team.id)))
        card = client.get(f"/api/teams/{franchise.team_id}/owner").json()
        assert card["season_year"] == new.year and card["last_review"]["year"] == season.year


def test_owners_go_with_the_league_and_out_with_the_export(db: Session, client: TestClient,
                                                          league: League, season: Season):
    from app.services.leagues import delete_league

    owners.ensure_owners(db, league)
    db.commit()
    export = client.get(f"/api/leagues/{league.id}/export").json()
    assert len(export["owners"]) == len(league.teams)
    assert len(export["owner_seasons"]) == len(league.teams)
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(Owner.id)) is None and db.scalar(select(OwnerSeason.id)) is None
