"""Milestone 14, part 4: AI direction and roster building
(docs/design/owners-and-front-offices.md §5)."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import direction as rules
from app.domain.draft import ai_value
from app.models import Contract, Franchise, FreeAgentOffer, League, Player, Season, Team
from app.services import direction, free_agency, offseason
from app.services.members import human_team_ids
from tests.conftest import rollover


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


class TestTheRules:
    def test_where_a_team_is_going(self):
        young, old = [25] * 22, [31] * 22
        assert rules.decide(2, 30, young, "build").direction == "contend"
        assert rules.decide(2, 30, old, "build").direction == "middle"  # (aging, patient owner)
        assert rules.decide(2, 30, old, "win_now").direction == "contend"
        assert rules.decide(28, 30, young, "profit").direction == "rebuild"
        assert rules.decide(28, 30, young, "win_now").direction == "middle"  # (won't wait)
        assert rules.decide(15, 30, young, "win_now").direction == "contend"
        assert rules.decide(15, 30, old, "build").direction == "rebuild"
        assert rules.decide(15, 30, young, "build").direction == "middle"
        why = rules.decide(1, 30, [26, 28], "profit").reasons
        assert why == ["1st of 30 by team rating", "Starters average 27.0 years old"]
        assert rules.decide(22, 30, young, "win_now").reasons[0] == "22nd of 30 by team rating"

    def test_building_to_match(self):
        assert rules.keeps("contend", 31, 68) and not rules.keeps("middle", 31, 68)
        assert not rules.keeps("rebuild", 29, 79) and rules.keeps("rebuild", 27, 60)
        assert not rules.wants_free_agent("rebuild", 31) and rules.wants_free_agent("contend", 34)
        assert rules.extension_reserve("contend", 8_000_000) == 8_000_000
        assert rules.extension_reserve("rebuild", 8_000_000) == 0

    def test_a_rebuilder_drafts_for_potential(self):
        raw, ready = (60, 85), (72, 74)  # (overall, potential), with the same noise
        assert ai_value(random.Random(1), *raw, False, 0.6) > ai_value(random.Random(1), *ready,
                                                                       False, 0.6)
        assert ai_value(random.Random(1), *raw, False, 0.3) < ai_value(random.Random(1), *ready,
                                                                       False, 0.3)


class TestFrontOffices:
    def test_ai_teams_decide_and_members_dont(self, db: Session, client: TestClient,
                                              league: League, franchise: Franchise):
        direction.decide(db, league)
        teams = db.scalars(select(Team).where(Team.league_id == league.id)).all()
        ai = [t for t in teams if t.id != franchise.team_id]
        assert all(t.direction in rules.DIRECTIONS and len(t.direction_reasons) >= 2 for t in ai)
        assert {t.direction for t in ai} >= {"contend", "rebuild"}
        assert db.get(Team, franchise.team_id).direction is None
        offices = client.get(f"/api/leagues/{league.id}/front-offices").json()
        mine = next(o for o in offices if o["team"]["id"] == franchise.team_id)
        assert mine["direction"] is None and mine["manager"] == "owner"
        theirs = next(o for o in offices if o["direction"] == "rebuild")
        assert theirs["label"] == "Rebuilding" and theirs["reasons"]

    def test_a_league_from_before_decides_on_first_read(self, client: TestClient,
                                                        league: League):
        offices = client.get(f"/api/leagues/{league.id}/front-offices").json()
        assert all(o["direction"] or o["manager"] for o in offices)

    def test_each_offseason_decides_again(self, db: Session, league: League, season: Season,
                                          franchise: Franchise):
        new = rollover(db, season)
        assert new.year == season.year + 1
        ai = db.scalars(select(Team).where(Team.league_id == league.id,
                                           Team.id != franchise.team_id)).all()
        assert all(t.direction is not None for t in ai)

    def test_on_autopilot_the_franchise_decides_too(self, db: Session, league: League,
                                                    franchise: Franchise):
        direction.decide(db, league, autopilot=True)
        assert db.get(Team, franchise.team_id).direction in rules.DIRECTIONS


def _ai_team(db: Session, league: League, franchise: Franchise) -> Team:
    return db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))


def _veteran(db: Session, team: Team, season: Season) -> Player:
    """A good 31-year-old whose contract ends this season."""
    player = db.scalar(select(Player).where(Player.team_id == team.id, Player.position == "WR")
                       .order_by(Player.overall.desc()))
    player.age, player.overall = 31, 75
    for contract in player.contracts:
        contract.is_active = False
    player.contracts.append(Contract(team_id=team.id, start_year=season.year, years=1,
                                     salary=5_000_000))
    db.flush()
    return player


class TestBuildingToMatch:
    @pytest.mark.parametrize("going, kept", [("contend", True), ("rebuild", False)])
    def test_re_signing(self, db: Session, league: League, franchise: Franchise,
                        season: Season, monkeypatch, going: str, kept: bool):
        team = _ai_team(db, league, franchise)
        veteran = _veteran(db, team, season)

        def everyone_goes(db_, league_, autopilot=False):
            for t in league_.teams:
                if t.id not in human_team_ids(db_, league_.id):
                    t.direction = going

        monkeypatch.setattr(direction, "decide", everyone_goes)
        season.phase = "offseason"
        offseason.advance(db, season)
        assert (db.get(Player, veteran.id).team_id == team.id) is kept

    def test_a_rebuilder_passes_on_older_free_agents(self, db: Session, league: League,
                                                     franchise: Franchise, season: Season):
        season.phase = "offseason"
        new = offseason.advance(db, season)  # (free agency's first day)
        for team in league.teams:
            if team.id != franchise.team_id:
                team.direction = "rebuild"
        market = free_agency._Market(db, new)
        free_agency._ai_offers(db, market)
        offers = db.scalars(select(FreeAgentOffer).where(FreeAgentOffer.season_id == new.id,
                                                         FreeAgentOffer.status == "pending"))
        ages = [db.get(Player, o.player_id).age for o in offers]
        assert ages and max(ages) <= rules.REBUILD_MAX_AGE

    def test_contenders_keep_room_for_next_years_raises(self, db: Session, league: League,
                                                        franchise: Franchise, season: Season):
        team = _ai_team(db, league, franchise)
        roster = db.scalars(select(Player).where(Player.team_id == team.id)).all()
        star = max(roster, key=lambda p: p.overall)
        for contract in star.contracts:
            contract.is_active = False
        star.contracts.append(Contract(team_id=team.id, start_year=season.year, years=1,
                                       salary=1_000_000))
        db.flush()
        assert direction.raises_due(roster, season.year, "contend") > 0
        assert direction.raises_due(roster, season.year + 5, "contend") == 0
