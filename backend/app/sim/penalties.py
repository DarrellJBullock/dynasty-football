"""Penalties: fouls before the snap and during the play, and how they're enforced. Pure.

Every foul has a base rate per snap (`Tuning.penalty_rates`), scaled by the awareness of
the players who could commit it: `factor = 1 + (center − awareness) × k`, held to
0.4–2.0, so a sharp line jumps half as often as an average one and a raw one twice as
often. One draw decides whether a foul of a kind the moment allows is called (the chances
are small, so two on one snap are left out); a second picks who, weighted by that factor.

Enforcement (design: docs/design/dynasty-mode.md §6):
- "replay": the play is wiped out and the down replayed from yards back (offensive fouls,
  called only on plays that gained ground, so the defense always accepts).
- "first": the play is wiped out; yards forward and an automatic first down (defensive
  holding and illegal contact, called only when the play gained less than the foul).
- "loss_of_down": intentional grounding (a throwaway under pressure with no receiver
  near): yards back, and the down counts.
- "after": the play stands; yards are added at its end with an automatic first down
  (personal fouls, called only when the play doesn't score or turn the ball over).
Pre-snap fouls are "replay" (offense) or yards forward (defense, a first down only if
they reach the line to gain). Pass interference is part of the pass itself (resolve.py).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.sim.resolve import Defense, Offense, Outcome
from app.sim.teams import SimPlayer
from app.sim.tuning import Tuning

Effect = Literal["replay", "first", "after", "pre_snap", "loss_of_down"]

NAMES = {
    "false_start": "False start",
    "delay_of_game": "Delay of game",
    "offside": "Offside",
    "neutral_zone_infraction": "Neutral zone infraction",
    "holding": "Offensive holding",
    "illegal_formation": "Illegal formation",
    "offensive_pass_interference": "Offensive pass interference",
    "intentional_grounding": "Intentional grounding",
    "defensive_holding": "Defensive holding",
    "illegal_contact": "Illegal contact",
    "pass_interference": "Defensive pass interference",
    "roughing_the_passer": "Roughing the passer",
    "unnecessary_roughness": "Unnecessary roughness",
    "face_mask": "Face mask",
}


@dataclass(frozen=True)
class Foul:
    kind: str
    team: Literal["offense", "defense"]
    yards: int
    effect: Effect


FOULS = {f.kind: f for f in (
    Foul("false_start", "offense", 5, "pre_snap"),
    Foul("delay_of_game", "offense", 5, "pre_snap"),
    Foul("offside", "defense", 5, "pre_snap"),
    Foul("neutral_zone_infraction", "defense", 5, "pre_snap"),
    Foul("holding", "offense", 10, "replay"),
    Foul("illegal_formation", "offense", 5, "replay"),
    Foul("offensive_pass_interference", "offense", 10, "replay"),
    Foul("intentional_grounding", "offense", 10, "loss_of_down"),
    Foul("defensive_holding", "defense", 5, "first"),
    Foul("illegal_contact", "defense", 5, "first"),
    Foul("roughing_the_passer", "defense", 15, "after"),
    Foul("unnecessary_roughness", "defense", 15, "after"),
    Foul("face_mask", "defense", 15, "after"),
)}


def factor(player: SimPlayer, t: Tuning) -> float:
    """How much more (or less) often than usual this player fouls, from his awareness."""
    awareness = player.ratings.get("awareness", t.penalty_awareness_center)
    return min(2.0, max(0.4, 1 + (t.penalty_awareness_center - awareness)
                        * t.penalty_awareness_k))


def _call(candidates: Sequence[tuple[str, Sequence[SimPlayer]]], rng: random.Random,
          t: Tuning) -> dict | None:
    """At most one of the candidate fouls: (kind, the players who could commit it)."""
    odds = []
    for kind, players in candidates:
        weights = [factor(p, t) for p in players]
        odds.append((kind, players, weights,
                     t.penalty_rates[kind] * sum(weights) / len(weights)))
    roll = rng.random()
    for kind, players, weights, chance in odds:
        if roll < chance:
            foul = FOULS[kind]
            player = rng.choices(players, weights)[0]
            return {"team": foul.team, "kind": kind, "yards": foul.yards,
                    "player": player.id, "effect": foul.effect}
        roll -= chance
    return None


def pre_snap(off: Offense, front: Sequence[SimPlayer], backers: Sequence[SimPlayer],
             rng: random.Random, t: Tuning) -> dict | None:
    """A foul before the snap (no play): false starts and delays on the offense, offside
    and neutral-zone infractions on the defense."""
    return _call([("false_start", off.line), ("delay_of_game", [off.qb]),
                  ("offside", [*front, *backers]), ("neutral_zone_infraction", front)],
                 rng, t)


def live(outcome: Outcome, off: Offense, deff: Defense, ball_on: int, rng: random.Random,
         t: Tuning) -> dict | None:
    """A foul during the play that the other side would accept (None: a clean play, or one
    already flagged for pass interference)."""
    if outcome.penalty or outcome.turnover or outcome.kind == "kneel":
        return None
    gained = outcome.yards
    passing = outcome.kind in ("pass", "sack")
    candidates: list[tuple[str, Sequence[SimPlayer]]] = []
    if gained > 0:
        candidates += [("holding", [*off.line, off.te]),
                       ("illegal_formation", [*off.line, *off.wrs, off.te])]
        if outcome.kind == "pass" and outcome.result == "complete":
            candidates.append(("offensive_pass_interference", [*off.wrs, off.te]))
    if outcome.result == "throwaway":
        candidates.append(("intentional_grounding", [off.qb]))
    if passing and gained < FOULS["defensive_holding"].yards:
        candidates += [("defensive_holding", [*deff.backers, *deff.corners, deff.fs, deff.ss]),
                       ("illegal_contact", deff.corners)]
    if 0 < ball_on + gained < 100:  # (not on a score or a safety)
        if outcome.kind == "pass":  # (after the throw: never on a sack)
            candidates.append(("roughing_the_passer", [*deff.front, *deff.olbs]))
        candidates.append(("unnecessary_roughness", deff.all))
        if outcome.result != "incomplete":  # (someone was tackled)
            candidates.append(("face_mask", deff.all))
    return _call(candidates, rng, t) if candidates else None
