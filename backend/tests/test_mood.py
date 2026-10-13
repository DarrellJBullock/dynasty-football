"""Milestone 15, part 1: personalities and mood (docs/design/players-and-storylines.md §3)."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import personality as rules
from app.models import Franchise, League, Player, Season
from app.schemas import SimulateRequest
from app.services import mood, offseason
from app.services import season as season_service
from app.services.teams import load_overrides, load_roster, team_lineup


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _situation(**kw) -> rules.Situation:
    base = {"role": "backup", "win_pct": None, "pay_ratio": None, "contract_year": False}
    return rules.Situation(**{**base, **kw})


STEADY = rules.Traits("steady", "team_player")


class TestTheRules:
    def test_traits_from_a_players_own_stream(self):
        made = [rules.make(rules.rng_for(1, pid), 25) for pid in range(400)]
        assert {t.drive for t in made} == set(rules.DRIVES)
        assert {t.temperament for t in made} == set(rules.TEMPERAMENTS)
        assert rules.make(rules.rng_for(1, 7), 25) == rules.make(rules.rng_for(1, 7), 25)
        veterans = [rules.make(random.Random(i), 31).temperament for i in range(2000)]
        rookies = [rules.make(random.Random(i), 22).temperament for i in range(2000)]
        assert veterans.count("leader") > rookies.count("leader") * 1.5

    def test_each_part_of_a_season(self):
        neutral = rules.Traits("steady", "leader")  # (a leader feels things as they are)
        assert rules.mood_parts(neutral, _situation(role="starter")) == [("Starting", 5)]
        assert rules.mood_parts(neutral, _situation(role="benched")) == [("Wants to start", -10)]
        assert rules.mood_parts(neutral, _situation(win_pct=1.0)) == [("The team's record", 10)]
        assert rules.mood_parts(neutral, _situation(pay_ratio=0.5)) == [("Underpaid", -8)]
        assert rules.mood_parts(neutral, _situation(pay_ratio=1.5)) == [("Well paid", 3)]
        assert rules.mood_parts(neutral, _situation(contract_year=True)) == [
            ("A contract year", -4)]
        assert rules.mood_parts(neutral, _situation(win_pct=0.5)) == []  # (nothing moved)

    def test_what_a_player_cares_about(self):
        losing = _situation(win_pct=0.0)
        assert dict(rules.mood_parts(rules.Traits("competitor", "leader"), losing))[
            "The team's record"] == -15
        assert dict(rules.mood_parts(rules.Traits("mercenary", "leader"), losing))[
            "The team's record"] == -5
        cheap = _situation(pay_ratio=0.5)
        assert dict(rules.mood_parts(rules.Traits("mercenary", "leader"), cheap))[
            "Underpaid"] == -12
        assert rules.mood_parts(rules.Traits("loyal", "leader"),
                                _situation(contract_year=True)) == []

    def test_temperament_scales_it_all(self):
        benched = _situation(role="benched")
        assert rules.mood_parts(rules.Traits("steady", "volatile"), benched) == [
            ("Wants to start", -15)]
        assert rules.mood_parts(STEADY, benched) == [("Wants to start", -8)]

    def test_moods_labels_and_next_season(self):
        assert rules.mood(60, [("Starting", 5), ("Underpaid", -8)]) == 57
        assert rules.mood(5, [("Wants to start", -15)]) == 0
        assert [rules.label(v) for v in (90, 60, 40, 10)] == [
            "Happy", "Content", "Unhappy", "Miserable"]
        assert rules.next_base(90) == 70 and rules.next_base(10) == 30


class TestPlayers:
    def test_everyone_gets_traits_once(self, db: Session, league: League):
        mood.ensure_traits(db, league.id)
        assert db.scalar(select(func.count(Player.id)).where(Player.drive.is_(None))) == 0
        player = db.scalar(select(Player).order_by(Player.id))
        assert (player.drive, player.temperament) == tuple(vars(rules.make(
            rules.rng_for(league.id, player.id), player.age)).values())
        before = {p.id: (p.drive, p.temperament) for p in db.scalars(select(Player))}
        mood.ensure_traits(db, league.id)
        assert {p.id: (p.drive, p.temperament) for p in db.scalars(select(Player))} == before

    def test_a_starters_mood_and_what_moved_it(self, db: Session, client: TestClient,
                                               franchise: Franchise):
        roster = load_roster(db, franchise.team_id)
        lineup = team_lineup(roster, load_overrides(db, [franchise.team_id])[franchise.team_id])
        starter = lineup[next(iter(lineup))][0]
        view = client.get(f"/api/players/{starter.id}/mood").json()
        assert view["role"] == "starter" and view["base"] == rules.START_MOOD
        assert view["drive"] in rules.DRIVES and view["drive_means"]
        assert view["mood"] == rules.clamp(view["base"] + sum(v for _, v in view["parts"]))
        assert view["label"] == rules.label(view["mood"])

    def test_a_backup_who_could_start_wants_to(self, db: Session, client: TestClient,
                                               franchise: Franchise):
        roster = load_roster(db, franchise.team_id)
        lineup = team_lineup(roster, load_overrides(db, [franchise.team_id])[franchise.team_id])
        starters = {p.id for ps in lineup.values() for p in ps}
        backup = next(p for p in roster if p.id not in starters and p.position == "WR")
        weakest = min(p.overall for pos, ps in lineup.items() if pos.value == "WR" for p in ps)
        backup.overall, backup.age = weakest - 1, 27
        db.commit()
        view = client.get(f"/api/players/{backup.id}/mood").json()
        assert view["role"] == "benched"
        assert any(label == "Wants to start" for label, _ in view["parts"])

    def test_a_free_agent_is_as_he_was(self, db: Session, client: TestClient, league: League):
        free = db.scalar(select(Player).where(Player.league_id == league.id,
                                              Player.team_id.is_(None),
                                              Player.is_prospect.is_(False)))
        view = client.get(f"/api/players/{free.id}/mood").json()
        assert view["role"] == "free_agent" and view["parts"] == []
        assert view["mood"] == view["base"]

    def test_the_locker_room(self, db: Session, client: TestClient, franchise: Franchise):
        room = client.get(f"/api/teams/{franchise.team_id}/locker-room").json()
        assert sum(room["counts"].values()) == len(load_roster(db, franchise.team_id))
        moods = [p["mood"] for p in room["unhappiest"]]
        assert moods == sorted(moods) and len(moods) <= 8
        assert 0 <= room["average"] <= 100

    def test_part_of_a_season_carries_into_the_next(self, db: Session, league: League,
                                                    franchise: Franchise, season: Season,
                                                    client: TestClient):
        season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"))
        season_service.simulate(db, season, SimulateRequest(until="end_of_playoffs"))
        db.commit()
        player = load_roster(db, franchise.team_id)[0]
        ended = client.get(f"/api/players/{player.id}/mood").json()["mood"]
        season.phase = "offseason"
        offseason.advance(db, season)
        db.refresh(player)
        assert player.mood_base == rules.next_base(ended)
