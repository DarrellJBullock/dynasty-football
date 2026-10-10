import pytest

from app.domain.contracts import MIN_SALARY, market_salary
from app.domain.positions import (
    JERSEY_RANGES,
    POSITION_GROUPS,
    ROSTER_MAX,
    ROSTER_TEMPLATE,
    STARTERS,
    Position,
    available_jersey,
)
from app.domain.ratings import (
    ATTRIBUTES,
    POSITION_WEIGHTS,
    calculate_overall,
    clamp_rating,
    key_attributes,
)


def uniform(value: int) -> dict[str, int]:
    return dict.fromkeys(ATTRIBUTES, value)


class TestPositions:
    def test_every_position_is_fully_configured(self):
        for table in (POSITION_GROUPS, ROSTER_TEMPLATE, POSITION_WEIGHTS, JERSEY_RANGES):
            assert set(table) == set(Position)

    def test_roster_template_fills_the_roster(self):
        assert sum(ROSTER_TEMPLATE.values()) == ROSTER_MAX

    def test_template_carries_enough_players_to_start(self):
        for position, starters in STARTERS.items():
            assert ROSTER_TEMPLATE[position] >= starters

    def test_available_jersey_prefers_conventional_range(self):
        assert available_jersey("QB", set()) == 1
        assert available_jersey("QB", {1, 2}) == 3
        assert available_jersey("WR", set(range(10, 20))) == 80

    def test_available_jersey_falls_back_to_any_free_number(self):
        taken = set(range(1, 20))
        assert available_jersey("K", taken) == 0


class TestRatings:
    @pytest.mark.parametrize("position", list(Position))
    def test_uniform_attributes_produce_that_overall(self, position):
        assert calculate_overall(position, uniform(73)) == 73

    def test_overall_uses_position_relevant_attributes(self):
        passer = uniform(40) | {"throw_power": 95, "throw_accuracy": 95, "awareness": 90}
        assert calculate_overall("QB", passer) >= 85
        # The same player graded as a cornerback is poor.
        assert calculate_overall("CB", passer) < 50

    def test_irrelevant_attributes_do_not_change_overall(self):
        base = uniform(70)
        boosted = base | {"kick_power": 99, "kick_accuracy": 99}
        assert calculate_overall("MLB", base) == calculate_overall("MLB", boosted)

    def test_clamp_rating(self):
        assert clamp_rating(-5) == 0
        assert clamp_rating(150) == 99
        assert clamp_rating(72.6) == 73

    def test_key_attributes_ordered_by_weight(self):
        assert key_attributes("QB")[0] == "throw_accuracy"
        assert key_attributes("K", limit=2) == ["kick_accuracy", "kick_power"]


class TestContracts:
    def test_minimum_salary_for_low_rated_players(self):
        assert market_salary(Position.WR, 50) == MIN_SALARY

    def test_salary_increases_with_overall(self):
        salaries = [market_salary(Position.CB, ovr) for ovr in range(55, 100, 5)]
        assert salaries == sorted(salaries)
        assert len(set(salaries)) == len(salaries)

    def test_quarterbacks_paid_more_than_kickers(self):
        assert market_salary(Position.QB, 85) > 3 * market_salary(Position.K, 85)
