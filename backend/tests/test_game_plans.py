import dataclasses
import hashlib
import json
import random
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from app.db import Base
from app.models import Franchise, League, Player, Team
from app.seed.generator import generate_league
from app.services.season import league_sim_teams
from app.sim import coaching
from app.sim.engine import simulate_game
from app.sim.gameplan import (
    DEFENSE_CHOICES,
    NEUTRAL,
    OFFENSE_CHOICES,
    GamePlan,
    TeamRatings,
    generated,
    validate,
)
from app.sim.playcalls import AICoach
from app.sim.state import GameState
from app.sim.teams import build_sim_team, team_from_dict, team_to_dict

# A whole-book, all-zero plan must make the calls the AI made before game plans:
# this is a game's play log as the engine played it then (pinned on SIM_VERSION 1.5,
# re-pinned on 1.7 and 1.8, whose penalties and fatigue change the draws around the calls).
NEUTRAL_GAME = "f8b4e2f65edcf380"

SPECIAL = {"kneel", "punt", "field_goal"}  # (situational calls, not plan choices)
LEAN = GamePlan(  # just what a plan must keep, and two blitzes
    offense=frozenset({"inside_zone", "toss", "bubble", "slants", "dig", "four_verts"}),
    defense=frozenset({"cover3", "cover1", "fire_zone"}))


@pytest.fixture(scope="module")
def pair():
    """Two teams of the default league (seed 2026), as the engine takes them."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        generate_league(session, seed=2026)
        session.flush()
        teams = session.scalars(select(Team).order_by(Team.id)).all()[:2]
        rosters = {t.id: session.scalars(select(Player).where(Player.team_id == t.id)
                                         .options(selectinload(Player.ratings))).all()
                   for t in teams}

        def build(index: int, plan: GamePlan | None = NEUTRAL):
            team = teams[index]
            return build_sim_team(team.id, team.abbreviation, team.full_name, rosters[team.id],
                                  {p.id: p.ratings.as_dict() for p in rosters[team.id]}, None,
                                  plan)
        yield build


def _log(result) -> str:
    plays = [p.to_dict() for p in result.plays]
    return hashlib.sha256(json.dumps(plays, sort_keys=True, default=str).encode()).hexdigest()[:16]


class TestTheAI:
    def test_a_neutral_plan_plays_as_before(self, pair):
        assert _log(simulate_game(pair(0), pair(1), seed=1000)) == NEUTRAL_GAME
        # Naming every play and call is the same as the whole book.
        whole = GamePlan(offense=frozenset(OFFENSE_CHOICES), defense=frozenset(DEFENSE_CHOICES))
        assert _log(simulate_game(pair(0, whole), pair(1, whole), seed=1000)) == NEUTRAL_GAME

    def test_calls_only_what_the_plan_has(self, pair):
        offense, defense = Counter(), Counter()
        for seed in range(6):
            result = simulate_game(pair(0, LEAN), pair(1), seed=seed)
            home = result.home.abbreviation
            for play in result.plays:
                mine = play.offense == home
                if mine and play.call and play.call.get("play"):
                    offense[play.call["play"]] += 1
                if not mine and play.defense and play.defense.get("play"):
                    defense[play.defense["play"]] += 1
        assert set(offense) - SPECIAL <= LEAN.offense
        assert set(defense) <= LEAN.defense
        assert len(set(offense) & LEAN.offense) >= 5  # (it uses the plan, not one play)

    def _rates(self, pair, plan: GamePlan, games: int = 8) -> Counter:
        counts = Counter()
        for seed in range(games):
            result = simulate_game(pair(0, plan), pair(1, plan), seed=seed)
            for play in result.plays:
                call, cover = play.call or {}, play.defense or {}
                if call.get("type") in ("run", "pass"):
                    counts["snaps"] += 1
                    counts["passes"] += call["type"] == "pass"
                    counts["deep"] += call.get("depth") == "deep"
                    counts["play_action"] += bool(call.get("play_action"))
                if "blitz" in cover:
                    counts["defense"] += 1
                    counts["blitz"] += cover["blitz"]
                    counts["man"] += cover["coverage"] == "man"
        return counts

    @pytest.mark.parametrize("tendency,count,base", [
        ("pass_rate", "passes", "snaps"), ("deep_shots", "deep", "passes"),
        ("play_action", "play_action", "passes"), ("blitz", "blitz", "defense"),
        ("man_coverage", "man", "defense")])
    def test_tendencies_move_the_mix(self, pair, tendency: str, count: str, base: str):
        low = self._rates(pair, GamePlan(tendencies={tendency: -2}))
        high = self._rates(pair, GamePlan(tendencies={tendency: 2}))
        assert high[count] / high[base] > low[count] / low[base] * 1.15

    def test_fourth_down_aggressiveness(self, pair):
        state = GameState(down=4, distance=2, ball_on=50, quarter=2, clock=600)
        def call(level: int) -> str:
            team = pair(0, GamePlan(tendencies={"fourth_down": level}))
            return AICoach().offense(state, team, pair(1), random.Random(1)).kind
        assert call(0) == "punt"
        assert call(2) in ("run", "pass")  # going for it
        state = GameState(down=4, distance=1, ball_on=50, quarter=2, clock=600)
        assert call(0) in ("run", "pass") and call(-2) == "punt"

    def test_going_for_two(self):
        down_one = GameState(quarter=4, clock=600, score={"home": 13, "away": 14})
        late_down_two = GameState(quarter=4, clock=200, score={"home": 12, "away": 14})
        def coach(level: int) -> AICoach:
            return AICoach({"home": GamePlan(tendencies={"two_point": level})})
        assert coach(0).conversion_call(down_one, "home") == "kick"
        assert coach(1).conversion_call(down_one, "home") == "two"
        assert coach(0).conversion_call(late_down_two, "home") == "two"
        assert coach(-1).conversion_call(late_down_two, "home") == "kick"


class TestPlans:
    def test_what_a_plan_must_keep(self):
        assert validate(NEUTRAL) == [] and validate(LEAN) == []
        thin = dataclasses.replace(LEAN, offense=LEAN.offense - {"four_verts"},
                                   defense=frozenset({"cover3"}))
        assert validate(thin) == ["The plan needs a deep pass.",
                                  "The plan needs a man coverage without a blitz."]
        odd = GamePlan(offense=frozenset({*LEAN.offense, "hail_mary"}),
                       tendencies={"blitz": 3, "trick_plays": 1})
        assert validate(odd) == ["Unknown plays: hail_mary.", "Blitzing goes from -2 to 2.",
                                 "Unknown tendency: trick_plays."]

    def test_generated_plans_lean_on_the_roster(self):
        assert generated(TeamRatings(arm_and_speed=85, pass_rush=60, man_coverage=72)) == \
            GamePlan(tendencies={"deep_shots": 1, "blitz": -1})
        assert generated(TeamRatings(74, 72, 72)) == NEUTRAL

    def test_snapshots_keep_the_plan(self, pair):
        team = pair(0, LEAN)
        assert team_from_dict(team_to_dict(team)).plan == LEAN
        older = team_to_dict(team)
        del older["plan"]  # (a coached game from before game plans)
        assert team_from_dict(older).plan == NEUTRAL


class TestTheApi:
    def test_view_save_and_reset(self, client: TestClient, db: Session, franchise: Franchise):
        url = f"/api/teams/{franchise.team_id}/game-plan"
        view = client.get(url).json()
        assert view["custom"] is False
        assert view["offense"] == OFFENSE_CHOICES and view["defense"] == DEFENSE_CHOICES
        assert set(view["tendencies"]) == set(view["tendency_labels"]) == set(view["suggested"])
        assert view["tendencies"] == view["suggested"]
        assert {r["label"] for r in view["required"]} >= {"an inside run", "a deep pass"}

        body = {"offense": sorted(LEAN.offense), "defense": sorted(LEAN.defense),
                "tendencies": {"pass_rate": 2, "blitz": -1}}
        saved = client.put(url, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json() == {**saved.json(), "custom": True, "offense": body["offense"]}
        assert saved.json()["tendencies"]["pass_rate"] == 2
        # The engine plays the franchise to it.
        teams = league_sim_teams(db, franchise.league_id)
        assert teams[franchise.team_id].plan == GamePlan(
            offense=LEAN.offense, defense=LEAN.defense, tendencies={"pass_rate": 2, "blitz": -1})

        reset = client.delete(url).json()
        assert reset["custom"] is False and reset["offense"] == OFFENSE_CHOICES

    def test_a_plan_that_cant_run_is_refused(self, client: TestClient, franchise: Franchise):
        response = client.put(f"/api/teams/{franchise.team_id}/game-plan",
                              json={"offense": ["inside_zone"], "defense": DEFENSE_CHOICES})
        assert response.status_code == 422
        assert "The plan needs an outside run." in response.json()["detail"]

    def test_only_your_own_team(self, client: TestClient, db: Session, league: League,
                                franchise: Franchise):
        other = db.scalar(select(Team).where(Team.league_id == league.id,
                                             Team.id != franchise.team_id))
        assert client.get(f"/api/teams/{other.id}/game-plan").status_code == 200
        response = client.put(f"/api/teams/{other.id}/game-plan",
                              json={"offense": OFFENSE_CHOICES, "defense": DEFENSE_CHOICES})
        assert response.status_code == 403


def test_coach_mode_suggestions_follow_the_plan(pair):
    """The AI calling for the user in Coach Mode (autopilot) sticks to the plan."""
    replay = coaching.replay(pair(0, LEAN), pair(1), seed=3, side="home", calls=[],
                             autopilot=True)
    called = {p.call["play"] for p in replay.plays
              if p.side == "home" and p.call and p.call.get("play")}
    assert called - SPECIAL <= LEAN.offense
