"""Playbooks: named plays as data, the AI calling them, and concepts that matter."""

import random
from statistics import mean

import pytest
from fastapi.testclient import TestClient

from app.sim import playbook
from app.sim.calibration import default_league_teams
from app.sim.engine import simulate_game
from app.sim.playbook import (
    AI_DEFENSES,
    AI_PASSES,
    AI_RUNS,
    AI_SHELL_MIX,
    DEFENSE,
    DEFENSE_BY_KEY,
    OFFENSE,
    OFFENSE_BY_KEY,
    concept_edge,
)
from app.sim.playcalls import DefenseCall, PlayCall
from app.sim.resolve import defense_personnel, offense_personnel, resolve_pass, resolve_run
from app.sim.tuning import DEFAULT_TUNING

SHELLS = {"cover0", "cover1", "two_man", "cover2", "tampa2", "cover3", "cover4", "fire_zone",
          "prevent"}


@pytest.fixture(scope="module")
def teams():
    return default_league_teams()


class TestPlaybookData:
    def test_keys_are_unique_and_shells_known(self):
        assert len(OFFENSE_BY_KEY) == len(OFFENSE) >= 20
        assert len(DEFENSE_BY_KEY) == len(DEFENSE) >= 10
        assert {p.shell for p in DEFENSE} <= SHELLS

    def test_every_play_is_a_complete_engine_call(self):
        for p in OFFENSE:
            if p.kind == "run":
                assert p.direction and not p.depth and p.category == "run"
            elif p.kind == "pass":
                assert p.depth and p.targets and len(p.targets) == 5
                assert p.play_action == (p.category == "play_action")
            else:
                assert p.category == "special"

    def test_concept_tables_name_real_plays_and_shells(self):
        for key, table in DEFAULT_TUNING.concept_edges.items():
            assert OFFENSE_BY_KEY[key].category != "special"
            assert set(table) <= SHELLS
        # Every run and pass concept has a table.
        named = {p.key for p in OFFENSE if p.category != "special"}
        assert named == set(DEFAULT_TUNING.concept_edges)

    def test_ai_choices_are_real_plays_that_match_the_coarse_call(self):
        for direction, options in AI_RUNS.items():
            for key, _ in options:
                assert OFFENSE_BY_KEY[key].direction == direction
        for (depth, play_action), options in AI_PASSES.items():
            for key, _ in options:
                assert OFFENSE_BY_KEY[key].depth == depth
                if depth != "screen":
                    assert OFFENSE_BY_KEY[key].play_action == play_action
        for (coverage, blitz), options in AI_DEFENSES.items():
            for key, _ in options:
                call = DEFENSE_BY_KEY[key]
                assert (call.coverage, call.blitz) == (coverage, blitz)
        assert sum(AI_SHELL_MIX.values()) == pytest.approx(1)

    def test_concepts_break_even_against_the_ai_mix(self):
        for key in DEFAULT_TUNING.concept_edges:
            expected = sum(concept_edge(DEFAULT_TUNING.concept_edges, key, shell) * share
                           for shell, share in AI_SHELL_MIX.items())
            assert expected == pytest.approx(0, abs=1e-9)
        # ...while the right call against the right shell still pays.
        edges = DEFAULT_TUNING.concept_edges
        assert concept_edge(edges, "smash", "cover2") > 0 > concept_edge(edges, "smash", "cover4")
        assert concept_edge(edges, "rb_screen", "cover0") > 0.3
        assert concept_edge(edges, "kneel", "cover2") == 0
        assert concept_edge(edges, None, "cover2") == concept_edge(edges, "smash", None) == 0

    def test_named_calls(self):
        assert PlayCall.named("pa_post") == PlayCall("pass", None, "deep", True, "pa_post")
        assert PlayCall.named("toss").describe() == {"type": "run", "direction": "outside",
                                                     "play": "toss"}
        cover0 = DefenseCall.named("cover0", "nickel")
        assert (cover0.coverage, cover0.blitz, cover0.package, cover0.shell) == (
            "man", True, "nickel", "cover0")
        assert DefenseCall.named("prevent", "base").package == "dime"
        assert DefenseCall().shell is None
        assert playbook.offense_name({"type": "pass", "play": "smash"}) == "Smash"
        assert playbook.offense_name({"type": "punt", "play": "punt"}) is None
        assert playbook.offense_name(None) is None
        assert playbook.defense_name({"play": "tampa2"}) == "Tampa 2"


class TestTheAICallsNamedPlays:
    def test_every_snap_has_a_named_call(self, teams):
        game = simulate_game(teams[0], teams[1], seed=11)
        snaps = [p for p in game.plays if p.call]
        assert snaps
        for play in snaps:
            assert play.call["play"] in OFFENSE_BY_KEY
            if play.defense:
                assert play.defense["play"] in DEFENSE_BY_KEY
        called = {p.call["play"] for p in snaps}
        assert len(called) >= 10  # a varied game plan

    def test_the_named_play_matches_the_coarse_call(self, teams):
        game = simulate_game(teams[2], teams[3], seed=5)
        for play in game.plays:
            if play.call and play.call["type"] in ("run", "pass"):
                named = OFFENSE_BY_KEY[play.call["play"]]
                assert named.kind == play.call["type"]
                assert named.direction == play.call.get("direction")
                assert named.depth == play.call.get("depth")


def _average(teams, resolve, call: PlayCall, dcall: DefenseCall, n: int = 4000) -> dict:
    rng = random.Random(3)
    offense, defense = teams[0], teams[1]
    gains, completions = [], []
    for _ in range(n):
        off = offense_personnel(offense, rng)
        deff = defense_personnel(defense, dcall, rng)
        outcome = resolve(call, dcall, off, deff, 30, 0.0, rng, DEFAULT_TUNING)
        gains.append(outcome.yards)
        completions.append(outcome.result == "complete")
    return {"yards": mean(gains), "completion": mean(completions)}


class TestConceptsMatter:
    def test_smash_beats_cover_2_and_struggles_against_quarters(self, teams):
        smash = PlayCall.named("smash")
        vs_cover2 = _average(teams, resolve_pass, smash, DefenseCall.named("cover2", "base"))
        vs_cover4 = _average(teams, resolve_pass, smash, DefenseCall.named("cover4", "base"))
        assert vs_cover2["completion"] > vs_cover4["completion"] + 0.04
        assert vs_cover2["yards"] > vs_cover4["yards"]

    def test_runs_gain_more_against_two_high_shells(self, teams):
        power = PlayCall.named("power")
        light = _average(teams, resolve_run, power, DefenseCall.named("cover4", "base"))
        loaded = _average(teams, resolve_run, power, DefenseCall.named("cover3", "base"))
        assert light["yards"] > loaded["yards"] + 0.4

    def test_a_play_steers_the_quarterback_to_its_target(self, teams):
        rng = random.Random(9)
        offense, defense = teams[0], teams[1]
        backs = 0
        for _ in range(600):
            off = offense_personnel(offense, rng)
            deff = defense_personnel(defense, DefenseCall(), rng)
            outcome = resolve_pass(PlayCall.named("rb_screen"), DefenseCall(), off, deff, 30, 0.0,
                                   rng, DEFAULT_TUNING)
            target = next((e.get("target") for e in outcome.events if e["t"] == "pass"), None)
            backs += target == off.rb.id
        assert backs > 300  # the back gets most screen throws


def test_playbook_api(client: TestClient):
    body = client.get("/api/playbook").json()
    assert [p["key"] for p in body["offense"]] == [p.key for p in OFFENSE]
    smash = next(p for p in body["offense"] if p["key"] == "smash")
    assert smash["name"] == "Smash" and smash["category"] == "intermediate"
    assert smash["depth"] == "medium" and len(smash["targets"]) == 5
    prevent = next(p for p in body["defense"] if p["key"] == "prevent")
    assert prevent["package"] == "dime" and prevent["shell"] == "prevent"
