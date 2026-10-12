"""Fatigue and substitutions (sim/fatigue.py; docs/design/depth-and-unity.md §3)."""

import dataclasses
from collections import Counter

import pytest

from app.domain.positions import Position as P
from app.sim import fatigue
from app.sim.calibration import default_league_teams
from app.sim.coaching import CoachCall, replay
from app.sim.engine import simulate_game
from app.sim.gameplan import GamePlan, TeamRatings, generated
from app.sim.stats import box_score
from app.sim.teams import HURT_ATTRIBUTES, SimPlayer, SimTeam
from app.sim.tuning import DEFAULT_TUNING

T = DEFAULT_TUNING


@pytest.fixture(scope="module")
def teams() -> list[SimTeam]:
    return default_league_teams()


def _player(pid: int, position: str = "RB", stamina: int = 70) -> SimPlayer:
    ratings = {"stamina": stamina, "speed": 85, "acceleration": 85, "agility": 85,
               "strength": 70, "awareness": 70, "toughness": 70}
    return SimPlayer(id=pid, name=f"P. {pid}", position=position, overall=75, ratings=ratings)


def _team(*slots: tuple[P, list[SimPlayer]], plan: GamePlan | None = None) -> SimTeam:
    depth = dict(slots)
    players = {p.id: p for _, ps in slots for p in ps}
    team = SimTeam(id=1, abbreviation="TST", name="Test", depth=depth, players=players)
    if plan:
        team.plan = plan
    team.start_game()
    return team


class TestEnergy:
    def test_a_snap_costs_by_position_and_stamina(self):
        back, sturdy, quarterback = _player(1), _player(2, stamina=95), _player(3, "QB")
        team = _team((P.RB, [back, sturdy]), (P.QB, [quarterback]))
        fatigue.after_snap(team, [1, 2, 3], 6, T)
        assert fatigue.energy(team, 1) == pytest.approx(100 - T.fatigue_cost["RB"] * 0.9)
        assert fatigue.energy(team, 2) > fatigue.energy(team, 1)  # more stamina, less tired
        assert fatigue.energy(team, 3) > fatigue.energy(team, 1)  # quarterbacks barely tire
        # A longer play costs more.
        long_team = _team((P.RB, [_player(1)]))
        fatigue.after_snap(long_team, [1], 12, T)
        one_snap = 100 - fatigue.energy(team, 1)
        assert 100 - fatigue.energy(long_team, 1) == pytest.approx(2 * one_snap)

    def test_players_recover_off_the_field_and_at_breaks(self):
        team = _team((P.RB, [_player(1), _player(2)]))
        for _ in range(3):
            fatigue.after_snap(team, [1], 6, T)
        tired = fatigue.energy(team, 1)
        fatigue.after_snap(team, [2], 6, T)  # a snap on the sideline
        assert fatigue.energy(team, 1) == pytest.approx(tired + T.fatigue_recover_snap)
        fatigue.recover(team, 100, T)
        assert team.energy == {} and not team.resting  # fresh again: nothing kept

    def test_a_tired_player_is_slower_and_more_likely_to_get_hurt(self):
        back = _player(1)
        team = _team((P.RB, [back]))
        assert fatigue.tired(team, back, T) is back
        team.energy[1] = 80.0
        tired = fatigue.tired(team, back, T)
        drop = int(20 / T.fatigue_points_per_rating)
        assert tired.id == back.id and fatigue.tired(team, back, T) is tired  # (cached)
        for attribute in HURT_ATTRIBUTES:
            assert tired.ratings[attribute] == back.ratings[attribute] - drop
        assert tired.ratings["awareness"] == back.ratings["awareness"]
        assert fatigue.injury_factor(team, 1, T) == pytest.approx(1 + T.fatigue_injury_k * 0.2)


class TestSubstitutions:
    def test_a_tired_starter_rests_until_he_recovers(self):
        starter, backup = _player(1), _player(2)
        team = _team((P.RB, [starter, backup]))
        assert [p.id for p in fatigue.take(team, P.RB, 1, [], T)] == [1]
        while 1 not in team.resting:
            fatigue.after_snap(team, [1], 6, T)
        assert fatigue.energy(team, 1) < T.fatigue_sub_out
        assert [p.id for p in fatigue.take(team, P.RB, 1, [], T)] == [2]
        # Back in only once above the sub-in line, not as soon as he's over the sub-out one.
        fatigue.recover(team, T.fatigue_sub_out - fatigue.energy(team, 1) + 1, T)
        assert [p.id for p in fatigue.take(team, P.RB, 1, [], T)] == [2]
        fatigue.recover(team, T.fatigue_sub_in, T)
        assert [p.id for p in fatigue.take(team, P.RB, 1, [], T)] == [1]

    def test_with_no_fresher_backup_the_tired_play_on(self):
        team = _team((P.DE, [_player(1, "DE"), _player(2, "DE"), _player(3, "DE")]))
        team.resting.update({1, 2})
        assert [p.id for p in fatigue.take(team, P.DE, 2, [], T)] == [1, 3]  # depth order
        team.resting.add(3)
        assert [p.id for p in fatigue.take(team, P.DE, 2, [], T)] == [1, 2]
        team.sidelined.update({1, 2, 3})  # nobody healthy: stand-ins
        assert all(p.id < 0 for p in fatigue.take(team, P.DE, 2, [], T))

    def test_quarterbacks_and_linemen_never_come_out_for_fatigue(self):
        team = _team((P.QB, [_player(1, "QB"), _player(2, "QB")]),
                     (P.OT, [_player(3, "OT"), _player(4, "OT"), _player(5, "OT")]))
        team.resting.update({1, 3})
        assert [p.id for p in fatigue.take(team, P.QB, 1, [], T)] == [1]
        assert [p.id for p in fatigue.take(team, P.OT, 2, [], T)] == [3, 4]

    def test_rotation_in_the_game_plan_moves_the_sub_out_line(self):
        heavy = _team((P.RB, [_player(1)]), plan=GamePlan(tendencies={"rotation": 2}))
        light = _team((P.RB, [_player(1)]), plan=GamePlan(tendencies={"rotation": -2}))
        assert fatigue.sub_out_line(heavy, T) == T.fatigue_sub_out + 2 * T.fatigue_rotation_step
        assert fatigue.sub_out_line(light, T) < T.fatigue_sub_out < fatigue.sub_out_line(heavy, T)

    def test_deep_rosters_get_plans_that_rotate_more(self):
        def plan(depth: float) -> GamePlan:
            return generated(TeamRatings(arm_and_speed=75, pass_rush=72, man_coverage=72,
                                         depth=depth))
        assert plan(74).level("rotation") == 1
        assert plan(65).level("rotation") == 0
        assert plan(55).level("rotation") == -1


def _snap_shares(game, team: SimTeam) -> Counter:
    snaps, total = Counter(), 0
    for play in game.plays:
        if play.personnel and play.down is not None and play.offense == team.abbreviation \
                and any(e["t"] != "penalty" for e in play.events):
            total += 1
            snaps.update(play.personnel["offense"])
    return Counter({pid: n / total for pid, n in snaps.items()})


class TestInGames:
    def test_backups_rotate_in_and_starters_play_most(self, teams):
        home, away = teams[0], teams[1]
        rb1, rb2 = (p.id for p in home.depth[P.RB][:2])
        qb = home.depth[P.QB][0].id
        backs, games = Counter(), 0
        for seed in range(8):
            game = simulate_game(home, away, seed=seed)
            if any(e["player"] in (qb, rb1, rb2) for e in game.injuries):
                continue  # (an injury, not fatigue, changes who plays)
            games += 1
            shares = _snap_shares(game, home)
            backs.update(shares)
            assert shares[qb] == 1.0  # the quarterback plays every snap
        assert games >= 4
        assert 0.55 < backs[rb1] / games < 0.9 and 0.1 < backs[rb2] / games < 0.45

    def test_tiring_teams_play_the_same_game_for_the_same_seed(self, teams):
        one = simulate_game(teams[2], teams[3], seed=11)
        two = simulate_game(teams[2], teams[3], seed=11)
        assert [p.to_dict() for p in one.plays] == [p.to_dict() for p in two.plays]

    def test_snap_counts_come_from_who_was_on_the_field(self, teams):
        game = simulate_game(teams[0], teams[1], seed=4)
        box = box_score(game)
        expected = Counter()
        for play in game.plays:
            snapped = any(e["t"] != "penalty" for e in play.events)
            if play.personnel and play.down is not None and snapped:
                expected.update(pid for pid in [*play.personnel["offense"],
                                                *play.personnel["defense"]] if pid > 0)
        assert {pid: line.snaps for pid, line in box.players.items() if line.snaps} == expected
        # A pre-snap foul isn't a snap.
        fouls = [p for p in game.plays if p.result.get("type") == "penalty"
                 and all(e["t"] == "penalty" for e in p.events)]
        assert all(p.personnel for p in fouls)

    def test_low_stamina_teams_wear_down(self, teams):
        def with_stamina(team: SimTeam, stamina: int) -> SimTeam:
            def change(p: SimPlayer) -> SimPlayer:
                return dataclasses.replace(p, ratings={**p.ratings, "stamina": stamina})
            return dataclasses.replace(
                team, depth={slot: [change(p) for p in ps] for slot, ps in team.depth.items()},
                players={pid: change(p) for pid, p in team.players.items()})

        def starter_share(stamina: int) -> float:
            team = with_stamina(teams[0], stamina)
            dl = [p.id for p in [*team.depth[P.DE][:2], *team.depth[P.DT][:2]]]
            on, total = 0, 0
            for seed in range(4):
                game = simulate_game(teams[1], team, seed=seed)
                for play in game.plays:
                    if play.personnel and play.down is not None \
                            and play.offense == teams[1].abbreviation:
                        total += 1
                        on += sum(pid in dl for pid in play.personnel["defense"])
            return on / (4 * total)

        assert starter_share(95) > starter_share(50) + 0.1


def test_coach_mode_shows_who_is_tired(teams):
    calls: list[CoachCall] = []
    situation = replay(teams[0], teams[1], 5, "home", calls).situation
    seen = []
    while situation and len(calls) < 40:
        if situation.role in ("offense", "defense"):
            seen.extend(situation.fatigue)
        calls.append(CoachCall(situation.role, situation.suggestion))
        situation = replay(teams[0], teams[1], 5, "home", calls).situation
    assert seen
    for line in seen:
        assert 0 <= line["energy"] < 100
        assert line["team"] in (teams[0].abbreviation, teams[1].abbreviation)
