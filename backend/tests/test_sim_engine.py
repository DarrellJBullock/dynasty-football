"""Simulation engine: determinism, game invariants, rules, AI decisions, and stats."""

import dataclasses
import random
from collections import Counter
from types import SimpleNamespace

import pytest

from app.domain.positions import Position
from app.sim.calibration import default_league_teams
from app.sim.engine import _Game, simulate_game
from app.sim.playcalls import AICoach, DefenseCall, PlayCall
from app.sim.state import GameState
from app.sim.stats import box_score
from app.sim.teams import SimTeam, build_sim_team
from app.sim.tuning import DEFAULT_TUNING


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


@pytest.fixture(scope="module")
def games(teams):
    rng = random.Random(42)
    return [simulate_game(*rng.sample(teams, 2), seed=i) for i in range(60)]


def _points_from_events(game) -> dict[str, int]:
    points = Counter()
    for play in game.plays:
        if play.result.get("touchdown"):
            points[play.side] += 6
        if play.result.get("defensive_td"):
            points["home" if play.side == "away" else "away"] += 6
        if play.result.get("safety"):
            points["home" if play.side == "away" else "away"] += 2
        for e in play.events:
            if e["t"] == "field_goal" and e["good"]:
                points[play.side] += 3
            elif e["t"] == "extra_point" and e["good"]:
                points[play.side] += 1
            elif e["t"] == "two_point" and e["good"]:
                points[play.side] += 2
    return points


class TestDeterminism:
    def test_same_seed_same_game(self, teams):
        a = simulate_game(teams[0], teams[1], seed=7)
        b = simulate_game(teams[0], teams[1], seed=7)
        assert [p.to_dict() for p in a.plays] == [p.to_dict() for p in b.plays]

    def test_different_seed_different_game(self, teams):
        a = simulate_game(teams[0], teams[1], seed=7)
        b = simulate_game(teams[0], teams[1], seed=8)
        assert [p.text for p in a.plays] != [p.text for p in b.plays]


class TestInvariants:
    def test_score_matches_scoring_plays(self, games):
        for game in games:
            points = _points_from_events(game)
            assert (points["home"], points["away"]) == (game.home_score, game.away_score)
            assert game.plays[-1].score == {"home": game.home_score, "away": game.away_score}

    def test_situations_are_legal(self, games):
        for game in games:
            last_quarter, last_clock = 1, 15 * 60
            for play in game.plays:
                minutes, seconds = map(int, play.clock.split(":"))
                clock = minutes * 60 + seconds
                assert play.quarter >= last_quarter
                if play.quarter == last_quarter:
                    assert clock <= last_clock, play.to_dict()
                last_quarter, last_clock = play.quarter, clock
                if play.down is not None:
                    assert 1 <= play.down <= 4
                    assert play.distance >= 1
                    assert 1 <= play.ball_on <= 99
                    assert play.distance <= 100 - play.ball_on

    def test_regulation_ends_with_a_winner_or_overtime(self, games):
        for game in games:
            final_quarter = game.plays[-1].quarter
            assert final_quarter >= 4
            if game.home_score == game.away_score:
                assert game.overtime

    def test_game_length(self, games):
        for game in games:
            scrimmage = sum(1 for p in game.plays if p.result.get("type") in
                            ("run", "pass", "sack", "scramble", "kneel"))
            assert 95 <= scrimmage <= 170
            regulation = sum(p.elapsed for p in game.plays if p.quarter <= 4)
            assert regulation <= 3600


class TestBoxScore:
    def test_box_score_is_internally_consistent(self, games):
        for game in games:
            box = box_score(game)
            for side in ("home", "away"):
                team = box.teams[side]
                mine = [line for pid, line in box.players.items() if box.player_team[pid] == side]
                assert team.points == (game.home_score if side == "home" else game.away_score)
                assert team.pass_cmp == sum(p.receptions for p in mine)
                assert team.pass_att == sum(p.pass_att for p in mine)
                passing = sum(p.pass_yds for p in mine)
                assert passing == sum(p.rec_yds for p in mine)
                assert team.pass_yds == passing - sum(p.sack_yds_lost for p in mine)
                assert team.rush_yds == sum(p.rush_yds for p in mine)

    def test_replacement_players_are_never_credited(self, games):
        for game in games:
            assert all(pid > 0 for pid in box_score(game).players)

    def test_penalty_plays_only_count_the_penalty(self, games):
        for game in games:
            box = box_score(game)
            penalties = sum(1 for p in game.plays for e in p.events if e["t"] == "penalty")
            assert sum(t.penalties for t in box.teams.values()) == penalties


class TestOvertime:
    def _ot_game(self, teams) -> _Game:
        game = _Game(teams[0], teams[1], seed=1, playoff=False, coaches=None,
                     tuning=DEFAULT_TUNING)
        game.s = GameState(quarter=5, clock=600)
        game.s.score = {"home": 17, "away": 17}
        return game

    def test_opening_touchdown_wins(self, teams):
        game = self._ot_game(teams)
        game.give_ball("home", 25)
        game.score("home", 6, "touchdown")
        assert game.over

    def test_field_goal_gives_the_other_team_a_chance(self, teams):
        game = self._ot_game(teams)
        game.give_ball("home", 25)
        game.score("home", 3, "field_goal")
        assert not game.over
        game.give_ball("away", 25)  # kickoff after the field goal
        game.give_ball("home", 40)  # away punts: possession 2 ends without answering
        assert game.over

    def test_matching_field_goals_go_to_sudden_death(self, teams):
        game = self._ot_game(teams)
        game.give_ball("home", 25)
        game.score("home", 3, "field_goal")
        game.give_ball("away", 25)
        game.score("away", 3, "field_goal")
        assert not game.over
        game.give_ball("home", 25)
        game.score("home", 3, "field_goal")
        assert game.over

    def test_scoreless_opening_possession_makes_it_next_score_wins(self, teams):
        game = self._ot_game(teams)
        game.give_ball("home", 25)
        game.give_ball("away", 30)  # home punted
        game.score("away", 3, "field_goal")
        assert game.over

    def test_playoff_games_never_end_tied(self, teams):
        even = [simulate_game(teams[3], teams[3], seed=i, playoff=True) for i in range(120)]
        assert all(g.home_score != g.away_score for g in even)
        assert any(g.overtime for g in even)


class TestCoaching:
    def test_custom_coach_controls_the_offense(self, teams):
        class RunEverything(AICoach):
            def offense(self, state, offense, defense, rng):
                call = super().offense(state, offense, defense, rng)
                return PlayCall("run", direction="inside") if call.kind == "pass" else call

        game = simulate_game(teams[0], teams[1], seed=3,
                             coaches={"home": RunEverything(), "away": AICoach()})
        home_passes = [p for p in game.plays if p.side == "home" and p.call
                       and p.call["type"] == "pass"]
        away_passes = [p for p in game.plays if p.side == "away" and p.call
                       and p.call["type"] == "pass"]
        assert home_passes == []
        assert away_passes

    @pytest.mark.parametrize("state, expected", [
        (dict(down=4, distance=8, ball_on=30), "punt"),
        (dict(down=4, distance=6, ball_on=80), "field_goal"),
        (dict(down=4, distance=1, ball_on=60), "run"),
        (dict(down=1, distance=10, ball_on=50, quarter=4, clock=60,
              score={"home": 24, "away": 17}, possession="home",
              timeouts={"home": 0, "away": 0}), "kneel"),
    ])
    def test_ai_situational_calls(self, teams, state, expected):
        team = teams[0]
        s = GameState(**state)
        calls = Counter(AICoach().offense(s, team, teams[1], random.Random(i)).kind
                        for i in range(40))
        assert calls.most_common(1)[0][0] == expected

    def test_defense_calls_fit_the_situation(self, teams):
        coach = AICoach()
        long = GameState(down=3, distance=12)
        short = GameState(down=2, distance=1)
        assert coach.defense(long, teams[0], teams[1], random.Random(1)).package == "dime"
        assert coach.defense(short, teams[0], teams[1], random.Random(1)).package == "base"
        assert isinstance(coach.defense(short, teams[0], teams[1], random.Random(1)),
                          DefenseCall)


def _roster(team: SimTeam, injured: set[int] = frozenset()):
    players = []
    for p in team.players.values():
        first, _, last = p.name.partition(". ")
        players.append(SimpleNamespace(id=p.id, first_name=first, last_name=last,
                                       position=p.position, overall=p.overall,
                                       injury_status="out" if p.id in injured else "healthy"))
    return players


class TestLineups:
    def test_injured_starter_does_not_play(self, teams):
        team = teams[0]
        starter = team.one(Position.QB)
        rebuilt = build_sim_team(team.id, team.abbreviation, team.name,
                                 _roster(team, {starter.id}),
                                 {pid: p.ratings for pid, p in team.players.items()})
        backup = rebuilt.one(Position.QB)
        assert backup.id != starter.id
        game = simulate_game(rebuilt, teams[1], seed=11)
        passers = {e["qb"] for p in game.plays if p.side == "home" for e in p.events
                   if e["t"] in ("pass", "sack")}
        assert passers == {backup.id}

    def test_custom_depth_order_is_used(self, teams):
        team = teams[0]
        qbs = [p.id for p in team.depth[Position.QB]]
        rebuilt = build_sim_team(team.id, team.abbreviation, team.name, _roster(team),
                                 {pid: p.ratings for pid, p in team.players.items()},
                                 {Position.QB: qbs[::-1]})
        assert rebuilt.one(Position.QB).id == qbs[-1]

    def test_empty_roster_still_plays_with_replacements(self, teams):
        empty = SimTeam(id=999, abbreviation="EMP", name="Empty", depth={})
        game = simulate_game(empty, teams[0], seed=5)
        assert game.away_score > game.home_score
        assert all(pid > 0 for pid in box_score(game).players)


class TestText:
    def test_play_by_play_reads_naturally(self, games):
        texts = [p.text for g in games for p in g.plays]
        assert all(t.endswith(".") for t in texts)
        assert any("pass complete to" in t for t in texts)
        assert any("TOUCHDOWN" in t for t in texts)
        assert any("field goal is GOOD" in t for t in texts)
        assert any("punts" in t for t in texts)

    def test_names_come_from_the_roster(self, teams):
        game = simulate_game(teams[0], teams[1], seed=2)
        names = {p.name for t in (teams[0], teams[1]) for p in t.players.values()}
        first = next(p for p in game.plays if p.call and p.call["type"] in ("run", "pass"))
        assert any(name in first.text for name in names)


def test_replace_preserves_tuning_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_TUNING.home_edge = 1.0  # type: ignore[misc]
