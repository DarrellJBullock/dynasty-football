"""Player attributes and position-weighted overall rating.

Attributes are 0-99. A player's overall (OVR) is the weighted average of the
attributes that matter for their position. The weights are intentionally
simple and transparent so custom-roster creators can reason about them.
"""

from collections.abc import Mapping

from app.domain.positions import Position

ATTRIBUTES: tuple[str, ...] = (
    # physical
    "speed", "acceleration", "strength", "agility", "stamina", "toughness",
    # mental
    "awareness",
    # passing
    "throw_power", "throw_accuracy",
    # ball carrier
    "carrying", "ball_carrier_vision", "elusiveness",
    # receiving
    "catching", "route_running",
    # blocking
    "run_blocking", "pass_blocking",
    # defense
    "tackling", "pass_rush", "block_shedding", "man_coverage", "zone_coverage",
    "play_recognition",
    # kicking
    "kick_power", "kick_accuracy",
)

RATING_MIN = 0
RATING_MAX = 99

POSITION_WEIGHTS: dict[Position, dict[str, float]] = {
    Position.QB: {"throw_power": 3, "throw_accuracy": 4, "awareness": 3,
                  "speed": 0.5, "agility": 0.5},
    Position.RB: {"speed": 2, "acceleration": 2, "agility": 1.5, "carrying": 1.5,
                  "ball_carrier_vision": 2, "elusiveness": 2, "strength": 0.5,
                  "catching": 0.5, "awareness": 1},
    Position.FB: {"run_blocking": 2.5, "strength": 2, "carrying": 1, "catching": 0.5,
                  "awareness": 1, "pass_blocking": 1},
    Position.WR: {"speed": 2, "catching": 3, "route_running": 3, "acceleration": 1,
                  "agility": 1, "awareness": 1},
    Position.TE: {"catching": 2, "route_running": 1.5, "run_blocking": 1.5,
                  "pass_blocking": 1, "strength": 1, "speed": 1, "awareness": 1},
    Position.OT: {"pass_blocking": 3, "run_blocking": 2.5, "strength": 2, "awareness": 1,
                  "agility": 0.5},
    Position.OG: {"run_blocking": 3, "pass_blocking": 2.5, "strength": 2.5, "awareness": 1},
    Position.C: {"run_blocking": 2.5, "pass_blocking": 2.5, "strength": 2, "awareness": 2},
    Position.DE: {"pass_rush": 3, "block_shedding": 2, "strength": 1.5, "speed": 1.5,
                  "tackling": 1, "play_recognition": 1},
    Position.DT: {"block_shedding": 3, "strength": 3, "pass_rush": 1.5, "tackling": 1.5,
                  "play_recognition": 1},
    Position.OLB: {"tackling": 2, "pass_rush": 1.5, "speed": 1.5, "play_recognition": 1.5,
                   "block_shedding": 1, "zone_coverage": 1},
    Position.MLB: {"tackling": 3, "play_recognition": 3, "block_shedding": 1,
                   "zone_coverage": 1, "speed": 1, "awareness": 1},
    Position.CB: {"man_coverage": 3, "zone_coverage": 2, "speed": 2.5, "acceleration": 1,
                  "agility": 1, "play_recognition": 1},
    Position.FS: {"zone_coverage": 3, "speed": 2, "play_recognition": 2, "man_coverage": 1,
                  "tackling": 1},
    Position.SS: {"tackling": 2, "zone_coverage": 2, "play_recognition": 2, "speed": 1.5,
                  "man_coverage": 1, "strength": 0.5},
    Position.K: {"kick_power": 3, "kick_accuracy": 4},
    Position.P: {"kick_power": 4, "kick_accuracy": 3},
}

for _weights in POSITION_WEIGHTS.values():
    assert set(_weights) <= set(ATTRIBUTES), _weights


def clamp_rating(value: float) -> int:
    return max(RATING_MIN, min(RATING_MAX, round(value)))


def calculate_overall(position: str, attributes: Mapping[str, int]) -> int:
    """Position-weighted average of the relevant attributes, rounded and clamped."""
    weights = POSITION_WEIGHTS[Position(position)]
    total = sum(weights.values())
    score = sum(attributes[name] * weight for name, weight in weights.items()) / total
    return clamp_rating(score)


def key_attributes(position: str, limit: int = 4) -> list[str]:
    """The most important attributes for a position, highest weight first."""
    weights = POSITION_WEIGHTS[Position(position)]
    return sorted(weights, key=lambda name: -weights[name])[:limit]
