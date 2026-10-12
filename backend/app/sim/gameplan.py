"""Game plans: which plays and calls a team runs, and its tendencies. Pure.

The AI calls plays as before (`playcalls.AICoach`: the situation sets the odds of run or
pass, the depth, play action, a blitz, man or zone), then picks a named play from the
team's plan. A plan with the whole book and every tendency at 0 makes exactly the calls
the AI made before plans existed, random draw for random draw. Design:
docs/design/dynasty-mode.md §4.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.sim.playbook import AI_DEFENSES, AI_PASSES, AI_RUNS, DEFENSE_BY_KEY, OFFENSE_BY_KEY

# Tendencies, each from -2 (much less) to +2 (much more); 0 is the league's usual.
TENDENCIES: dict[str, str] = {
    "pass_rate": "Run or pass",
    "deep_shots": "Deep shots",
    "play_action": "Play action",
    "blitz": "Blitzing",
    "man_coverage": "Man coverage",
    "fourth_down": "Going for it on fourth down",
    "two_point": "Going for two",
}
LEVELS = range(-2, 3)

# What one step of a tendency changes.
PASS_RATE_STEP = 0.05  # pass probability per level
DEEP_STEP = 0.35  # deep-pass weight, ×(1 + step × level)
PLAY_ACTION_STEP = 0.4  # play-action rate, ×(1 + step × level)
BLITZ_STEP = 0.35  # blitz rate, ×(1 + step × level)
MAN_STEP = 0.08  # man-coverage probability per level

# The calls a plan must keep, so the AI can answer every situation: a run inside and
# outside, a screen, a short, medium and deep pass (play action is optional), and a man
# and a zone call that don't blitz (blitzes are optional).
REQUIRED_OFFENSE = {
    "an inside run": AI_RUNS["inside"], "an outside run": AI_RUNS["outside"],
    "a screen": AI_PASSES[("screen", False)], "a short pass": AI_PASSES[("short", False)],
    "a medium pass": AI_PASSES[("medium", False)], "a deep pass": AI_PASSES[("deep", False)],
}
REQUIRED_DEFENSE = {
    "a zone coverage without a blitz": AI_DEFENSES[("zone", False)],
    "a man coverage without a blitz": AI_DEFENSES[("man", False)],
}
# The plays and calls the AI ever picks (the rest, like kicks, aren't plan choices).
OFFENSE_CHOICES = sorted({k for options in [*AI_RUNS.values(), *AI_PASSES.values()]
                          for k, _ in options})
DEFENSE_CHOICES = sorted({k for options in AI_DEFENSES.values() for k, _ in options})


@dataclass(frozen=True)
class GamePlan:
    offense: frozenset[str] | None = None  # None: the whole book
    defense: frozenset[str] | None = None
    tendencies: Mapping[str, int] = field(default_factory=dict)  # missing: 0

    def level(self, name: str) -> int:
        return self.tendencies.get(name, 0)

    def to_dict(self) -> dict:
        return {"offense": sorted(self.offense) if self.offense is not None else None,
                "defense": sorted(self.defense) if self.defense is not None else None,
                "tendencies": {k: v for k, v in self.tendencies.items() if v}}

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "GamePlan":
        if not data:
            return NEUTRAL
        return cls(offense=frozenset(data["offense"]) if data.get("offense") is not None else None,
                   defense=frozenset(data["defense"]) if data.get("defense") is not None else None,
                   tendencies=dict(data.get("tendencies") or {}))


NEUTRAL = GamePlan()


def validate(plan: GamePlan) -> list[str]:
    """What's wrong with a plan, as sentences (empty if nothing)."""
    errors = []
    for chosen, book, kind in ((plan.offense, OFFENSE_CHOICES, "play"),
                               (plan.defense, DEFENSE_CHOICES, "call")):
        unknown = sorted((chosen or set()) - set(book))
        if unknown:
            errors.append(f"Unknown {kind}s: {', '.join(unknown)}.")
    for chosen, required in ((plan.offense, REQUIRED_OFFENSE), (plan.defense, REQUIRED_DEFENSE)):
        if chosen is None:
            continue
        for what, options in required.items():
            if not any(key in chosen for key, _ in options):
                errors.append(f"The plan needs {what}.")
    for name, level in plan.tendencies.items():
        if name not in TENDENCIES:
            errors.append(f"Unknown tendency: {name}.")
        elif level not in LEVELS:
            errors.append(f"{TENDENCIES[name]} goes from -2 to 2.")
    return errors


def pick(options: list[tuple[str, float]], enabled: frozenset[str] | None,
         rng: random.Random) -> str | None:
    """A weighted pick among the options the plan has (None if it has none of them). With
    every option enabled this is the same draw as before plans."""
    if enabled is not None:
        options = [(k, w) for k, w in options if k in enabled]
        if not options:
            return None
    return rng.choices([k for k, _ in options], [w for _, w in options])[0]


def scaled(rate: float, step: float, level: int) -> float:
    """A rate moved by a tendency: ×(1 + step × level), so 0 leaves it exactly as is."""
    return rate * (1 + step * level) if level else rate


def generated(ratings: "TeamRatings") -> GamePlan:
    """The plan an AI team plays to: the whole book, leaning on its strengths. A strong
    arm and fast receivers take more deep shots; pass rushers blitz more; good corners
    play more man."""
    tendencies = {
        "deep_shots": _lean(ratings.arm_and_speed, 80, 70),
        "blitz": _lean(ratings.pass_rush, 78, 66),
        "man_coverage": _lean(ratings.man_coverage, 78, 66),
    }
    return GamePlan(tendencies={k: v for k, v in tendencies.items() if v})


def _lean(value: float, high: float, low: float) -> int:
    return 1 if value >= high else -1 if value <= low else 0


@dataclass(frozen=True)
class TeamRatings:
    """The few numbers a generated plan is drawn from (starters' averages)."""
    arm_and_speed: float  # the QB's arm with the top receivers' speed
    pass_rush: float  # edge rushers' and linebackers' pass rush
    man_coverage: float  # the starting corners' man coverage


def describe_book() -> dict:
    """The plays and calls a plan chooses from, by key (for the API)."""
    return {"offense": [OFFENSE_BY_KEY[k] for k in OFFENSE_CHOICES],
            "defense": [DEFENSE_BY_KEY[k] for k in DEFENSE_CHOICES]}
