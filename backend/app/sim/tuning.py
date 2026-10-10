"""Calibration constants for play resolution.

Probabilities use sigmoid(base + k * rating_difference), with ratings as z-scores
(70 → 0, 80 → +1). Tests in tests/test_sim_calibration.py hold league-wide output to the
targets in docs/design/simulation-engine.md §7; adjust these values, not the resolvers,
when calibrating.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tuning:
    # Home-field advantage, added to the home side's matchup scores (≈ +1.5 points).
    home_edge: float = 0.07

    # Running
    run_mu: float = 3.75
    run_sd: float = 3.3
    run_push_k: float = 0.9
    run_carrier_k: float = 0.55
    run_light_box: dict[str, float] = field(
        default_factory=lambda: {"base": 0.0, "nickel": 0.45, "dime": 0.9})
    breakaway_base: float = -2.5
    breakaway_k: float = 0.6
    breakaway_mean: float = 13.0
    fumble_rate: float = 0.024

    # Pass protection
    sack_base: float = -2.45
    sack_k: float = 0.75
    blitz_bonus: float = 0.55
    pressure_base: float = -1.15
    pressure_k: float = 0.7
    scramble_rate: float = 0.22

    # Coverage and throwing
    open_sd: float = 0.85
    completion_base: dict[str, float] = field(default_factory=lambda: {
        "screen": 1.45, "short": 0.6, "medium": -0.25, "deep": -1.2})
    completion_accuracy_k: float = 0.32
    completion_open_k: float = 0.55
    completion_catch_k: float = 0.22
    completion_pressure: float = 0.55
    interception_base: dict[str, float] = field(default_factory=lambda: {
        "screen": -4.85, "short": -3.8, "medium": -3.2, "deep": -2.6})
    interception_open_k: float = 0.55
    yac_mean: dict[str, float] = field(default_factory=lambda: {
        "screen": 4.5, "short": 2.8, "medium": 2.3, "deep": 2.5})

    # Obvious passing downs (3rd/4th and 5+): defense plays the sticks and pins its ears back
    passing_down_coverage: float = 0.6
    passing_down_rush: float = 0.3

    # Red zone (scaled up as the offense nears the goal line)
    red_zone_pass: float = 1.2
    end_zone_throw: float = 1.0
    red_zone_run: float = 2.6

    # Pace: seconds between snaps while the clock runs (normal / hurry-up / bleeding)
    runoff: tuple[int, int] = (31, 37)
    runoff_hurry: int = 12
    runoff_bleed: int = 39

    # Penalties
    false_start_rate: float = 0.011
    holding_rate: float = 0.022
    pass_interference_rate: float = 0.055  # of medium/deep incompletions

    # Kicking
    field_goal_base: float = 2.6
    field_goal_k: float = 0.95
    punt_gross: float = 45.0
    punt_sd: float = 5.5
    punt_fair_catch: float = 0.42
    punt_return_mean: float = 9.0
    kickoff_touchback: float = 0.62
    kickoff_return_spot: float = 27.0


DEFAULT_TUNING = Tuning()
