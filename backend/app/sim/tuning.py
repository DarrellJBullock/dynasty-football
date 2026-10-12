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
    read_bonus: tuple[float, ...] = (0.6, 0.25)  # preference for the 1st and 2nd reads
    screen_open: float = 1.6  # a screen's designed target is open by design, not by route
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

    # Play concepts against coverage shells (app/sim/playbook.py): raw edges for the
    # offense, centered at use against the AI's shell mix so each play breaks even on
    # average. Passes add the edge to every receiver's openness; runs add it, times
    # `concept_run_k` yards, to the expected gain. Two-high shells (Cover 2, 4, Tampa 2,
    # 2-Man, prevent) leave a lighter box; single-high shells and blitzes load it.
    concept_pass_k: float = 1.0
    concept_run_k: float = 1.4
    concept_edges: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "inside_zone": {"cover2": 0.2, "tampa2": 0.1, "cover4": 0.2, "two_man": 0.2,
                        "prevent": 0.4, "cover1": -0.15, "cover3": -0.1, "cover0": -0.25,
                        "fire_zone": -0.2},
        "power": {"cover2": 0.25, "cover4": 0.25, "two_man": 0.2, "prevent": 0.4,
                  "cover1": -0.15, "cover3": -0.15, "cover0": -0.2, "fire_zone": -0.15},
        "counter": {"cover0": 0.25, "fire_zone": 0.2, "cover1": 0.1, "cover3": -0.15,
                    "tampa2": -0.1},
        "draw": {"cover0": 0.3, "fire_zone": 0.3, "prevent": 0.45, "cover2": 0.2,
                 "tampa2": 0.15, "cover1": -0.2, "cover3": -0.2},
        "outside_zone": {"cover4": 0.2, "two_man": 0.15, "cover2": -0.15, "fire_zone": -0.2,
                         "cover0": 0.1},
        "toss": {"cover0": 0.25, "cover1": 0.1, "fire_zone": -0.25, "cover2": -0.2},
        "slants": {"cover3": 0.3, "cover4": 0.2, "cover0": 0.2, "prevent": 0.3,
                   "cover1": -0.1, "two_man": -0.3, "tampa2": -0.15},
        "stick": {"cover3": 0.25, "cover2": 0.1, "prevent": 0.25, "cover1": -0.2,
                  "two_man": -0.2},
        "hitches": {"cover3": 0.25, "cover4": 0.25, "prevent": 0.35, "cover0": -0.1,
                    "cover2": -0.2, "two_man": -0.2},
        "curl_flat": {"cover3": 0.2, "tampa2": 0.1, "prevent": 0.2, "cover2": -0.15,
                      "cover1": -0.2},
        "mesh": {"cover1": 0.35, "cover0": 0.3, "two_man": 0.2, "cover3": -0.15,
                 "tampa2": -0.3, "cover2": -0.1},
        "smash": {"cover2": 0.4, "tampa2": 0.15, "cover4": -0.25, "cover1": -0.15},
        "flood": {"cover3": 0.35, "fire_zone": 0.15, "cover2": -0.1, "cover1": -0.25,
                  "two_man": -0.2},
        "dig": {"cover4": 0.25, "cover2": 0.15, "tampa2": -0.25, "cover1": -0.1},
        "y_cross": {"cover1": 0.25, "cover3": 0.15, "cover2": -0.15, "tampa2": -0.25},
        "four_verts": {"cover3": 0.3, "cover0": 0.3, "cover2": 0.1, "cover4": -0.4,
                       "prevent": -0.5},
        "post_wheel": {"cover1": 0.25, "cover3": 0.2, "cover4": -0.3, "two_man": -0.2,
                       "prevent": -0.4},
        "pa_boot": {"cover3": 0.2, "cover1": 0.1, "fire_zone": -0.2, "cover0": -0.15},
        "pa_crossers": {"cover3": 0.25, "cover1": 0.2, "tampa2": -0.25, "cover2": -0.1},
        "pa_post": {"cover1": 0.3, "cover0": 0.35, "cover3": 0.1, "cover4": -0.3,
                    "cover2": -0.1, "prevent": -0.4},
        "rb_screen": {"cover0": 0.5, "fire_zone": 0.35, "cover1": 0.15, "cover2": -0.2,
                      "tampa2": -0.3, "cover4": -0.2},
        "bubble": {"cover3": 0.3, "cover4": 0.3, "prevent": 0.4, "cover2": -0.3,
                   "two_man": -0.3, "cover1": -0.15},
    })

    # Penalties (sim/penalties.py): base chance per snap of each foul, for players of
    # average awareness; each point of awareness below the center adds k (×0.4–×2.0).
    penalty_rates: dict[str, float] = field(default_factory=lambda: {
        "false_start": 0.017, "delay_of_game": 0.004,
        "offside": 0.008, "neutral_zone_infraction": 0.005,
        "holding": 0.034, "illegal_formation": 0.006, "offensive_pass_interference": 0.008,
        "intentional_grounding": 0.12,  # of throwaways
        "defensive_holding": 0.02, "illegal_contact": 0.008,
        "roughing_the_passer": 0.004, "unnecessary_roughness": 0.005, "face_mask": 0.003,
    })
    penalty_awareness_center: float = 72.0
    penalty_awareness_k: float = 0.03
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
    # Onside kicks: recovery odds sigmoid(base + k·kicker accuracy + k·(hands difference)),
    # about one in eight; squibs bounce to the receivers' 15–45 and can't be returned far.
    onside_base: float = -2.0
    onside_kick_k: float = 0.35
    onside_hands_k: float = 0.3
    squib_return_spot: float = 32.0
    squib_sd: float = 5.0

    # Injuries: per-snap chance for each player on the field (scaled by toughness), and the
    # multiplier for players in contact (ball carriers, tacklers, sacked QBs).
    injury_rate: float = 0.001
    injury_contact_factor: float = 3.0
    # Proneness: each earlier injury in a player's career adds this much (up to the cap).
    injury_history_k: float = 0.08
    injury_history_cap: int = 5
    # A questionable player plays hurt: his physical ratings drop by this many points.
    questionable_drop: int = 6

    # Fatigue (sim/fatigue.py). Energy cost per snap on the field by listed position, for a
    # snap of `fatigue_typical_snap` seconds, ×(stamina_base − stamina/100) (at least 0.4).
    fatigue_cost: dict[str, float] = field(default_factory=lambda: {
        "QB": 0.6, "RB": 7.0, "FB": 3.0, "WR": 2.6, "TE": 2.6,
        "OT": 0.8, "OG": 0.8, "C": 0.8,
        "DE": 6.5, "DT": 7.0, "OLB": 3.5, "MLB": 2.4, "CB": 2.2, "FS": 1.8, "SS": 2.0,
        "K": 0.0, "P": 0.0,
    })
    fatigue_typical_snap: float = 6.0
    fatigue_stamina_base: float = 1.6
    fatigue_recover_snap: float = 5.0  # each snap off the field
    fatigue_recover_change: float = 8.0  # a change of possession
    fatigue_recover_timeout: float = 4.0
    fatigue_recover_quarter: float = 8.0
    fatigue_recover_half: float = 60.0
    # Sub out below this (plus the plan's Rotation × step); back in at or above sub_in.
    fatigue_sub_out: float = 72.0
    fatigue_rotation_step: float = 4.0
    fatigue_sub_in: float = 90.0
    fatigue_points_per_rating: float = 4.0  # energy lost per point off physical ratings
    fatigue_injury_k: float = 0.5  # injury odds ×(1 + k × share of energy lost)


DEFAULT_TUNING = Tuning()
