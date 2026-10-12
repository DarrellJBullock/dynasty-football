"""Play calls and the situational AI coach.

`Coach` is the seam for Coach Mode: the engine asks a coach for each call, and a future
human coach can answer instead of `AICoach`.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.positions import Position
from app.sim.gameplan import (
    BLITZ_STEP,
    DEEP_STEP,
    MAN_STEP,
    PASS_RATE_STEP,
    PLAY_ACTION_STEP,
    GamePlan,
    pick,
    scaled,
)
from app.sim.playbook import AI_DEFENSES, AI_PASSES, AI_RUNS, DEFENSE_BY_KEY, OFFENSE_BY_KEY
from app.sim.state import GameState
from app.sim.teams import SimTeam

RunDirection = Literal["inside", "outside"]
PassDepth = Literal["screen", "short", "medium", "deep"]
Package = Literal["base", "nickel", "dime"]
Coverage = Literal["man", "zone"]
KickoffChoice = Literal["normal", "squib", "onside"]
ConversionChoice = Literal["kick", "two"]


@dataclass(frozen=True)
class PlayCall:
    kind: Literal["run", "pass", "punt", "field_goal", "kneel"]
    direction: RunDirection | None = None
    depth: PassDepth | None = None
    play_action: bool = False
    play: str | None = None  # the named play (app/sim/playbook.py), if any
    audible_from: str | None = None  # the play called in the huddle, if changed at the line

    @classmethod
    def named(cls, key: str, audible_from: str | None = None) -> "PlayCall":
        p = OFFENSE_BY_KEY[key]
        return cls(p.kind, p.direction, p.depth, p.play_action, key, audible_from)

    def describe(self) -> dict:
        data: dict = {"type": self.kind}
        if self.direction:
            data["direction"] = self.direction
        if self.depth:
            data["depth"] = self.depth
        if self.play_action:
            data["play_action"] = True
        if self.play:
            data["play"] = self.play
        if self.audible_from:
            data["audible_from"] = self.audible_from
        return data


@dataclass(frozen=True)
class DefenseCall:
    package: Package = "base"
    coverage: Coverage = "zone"
    blitz: bool = False
    play: str | None = None  # the named call (app/sim/playbook.py), if any
    audible_from: str | None = None  # the call made in the huddle, if changed at the line

    @property
    def shell(self) -> str | None:
        return DEFENSE_BY_KEY[self.play].shell if self.play else None

    @classmethod
    def named(cls, key: str, package: Package, audible_from: str | None = None) -> "DefenseCall":
        p = DEFENSE_BY_KEY[key]
        return cls(p.package or package, p.coverage, p.blitz, key, audible_from)

    def describe(self) -> dict:
        data: dict = {"package": self.package, "coverage": self.coverage, "blitz": self.blitz}
        if self.play:
            data["play"] = self.play
        if self.audible_from:
            data["audible_from"] = self.audible_from
        return data


def _other(side: str) -> str:
    return "away" if side == "home" else "home"


class Coach(Protocol):
    def offense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> PlayCall: ...

    def defense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> DefenseCall: ...

    def timeout(self, state: GameState, side: str) -> bool:
        """Before a snap with the clock running: stop it with a timeout?"""
        ...

    def kickoff_call(self, state: GameState, side: str) -> KickoffChoice:
        """Kicking off: a normal kick, a squib, or an onside kick?"""
        ...

    def conversion_call(self, state: GameState, side: str) -> ConversionChoice:
        """After a touchdown: kick the extra point, or go for two?"""
        ...


def field_goal_distance(ball_on: int) -> int:
    """Kick distance from the offense's spot: line to goal + 10 (end zone) + 7 (hold)."""
    return 100 - ball_on + 17


def kicker_range(team: SimTeam) -> int:
    return round(52 + 4 * team.one(Position.K).r("kick_power"))


class AICoach:
    """Situational play calling for both sides of the ball, within each team's game plan
    (`gameplan.py`: its plays and calls, and its tendencies). Plans for the kickoff and
    conversion decisions come in here, by side; play calls read each team's own."""

    def __init__(self, plans: Mapping[str, GamePlan] | None = None):
        self.plans = dict(plans or {})

    def offense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> PlayCall:
        s = state
        if self._should_kneel(s):
            return PlayCall.named("kneel")
        in_range = field_goal_distance(s.ball_on) <= kicker_range(offense)
        # Last snap of a half: take the points if the kick is makeable.
        if s.end_of_half and s.half_seconds_left <= 6 and in_range and s.margin <= 2:
            return PlayCall.named("field_goal")
        if s.down == 4:
            return self._fourth_down(s, offense, in_range, rng)
        return self._scrimmage(s, offense, rng)

    def defense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> DefenseCall:
        s = state
        plan = defense.plan
        passing_down = (s.down >= 3 and s.distance >= 6) or self._hurry(s, defending=True)
        package = self.package(s)
        blitz_rate = scaled(0.30 if passing_down else 0.24 if s.distance <= 2 else 0.17,
                            BLITZ_STEP, plan.level("blitz"))
        man_rate = 0.45 + MAN_STEP * plan.level("man_coverage")
        coverage: Coverage = "man" if rng.random() < man_rate else "zone"
        blitz = rng.random() < blitz_rate
        call = (pick(AI_DEFENSES[(coverage, blitz)], plan.defense, rng)
                or pick(AI_DEFENSES[(coverage, False)], plan.defense, rng))
        return DefenseCall.named(call, package)

    @classmethod
    def package(cls, s: GameState) -> Package:
        """Personnel to match the situation: dime on 3rd and long, nickel on passing downs."""
        passing_down = (s.down >= 3 and s.distance >= 6) or cls._hurry(s, defending=True)
        if s.down >= 3 and s.distance >= 10:
            return "dime"
        if passing_down or s.distance >= 8:
            return "nickel"
        return "base"

    @classmethod
    def timeout(cls, s: GameState, side: str) -> bool:
        """The offense saves time in its two-minute drill; a defense trailing late stops the
        clock to get the ball back."""
        if side == s.offense:
            return cls._hurry(s)
        return s.quarter >= 4 and not s.in_overtime and s.margin > 0 and s.game_seconds_left <= 180

    @staticmethod
    def kickoff_call(s: GameState, side: str) -> KickoffChoice:
        """Onside when trailing by two scores or less in the last four minutes; squib at the
        end of a half so there's no time for a long return."""
        behind = s.score[_other(side)] - s.score[side]
        if s.quarter == 4 and 0 < behind <= 16 and s.game_seconds_left <= 240:
            return "onside"
        if s.quarter in (2, 4) and s.clock <= 20:
            return "squib"
        return "normal"

    def conversion_call(self, s: GameState, side: str) -> ConversionChoice:
        """Go for two late when it ties the game or pulls within a field goal. A plan
        that likes going for two also goes to win (down one) or to go up three, from the
        start of the fourth quarter (or, at its most, the third); one that doesn't, never."""
        margin = s.score[side] - s.score[_other(side)]
        level = self.plans[side].level("two_point") if side in self.plans else 0
        if level < 0:
            return "kick"
        if level == 0:
            late = s.quarter == 4 and s.game_seconds_left <= 300
            return "two" if late and margin in (-2, -5) else "kick"
        late = s.quarter >= (3 if level >= 2 else 4)
        return "two" if late and margin in (-2, -5, -1, 1) else "kick"

    # ---------- offense helpers ----------

    @staticmethod
    def _hurry(s: GameState, defending: bool = False) -> bool:
        """Two-minute drill: end of a half, and (for the offense) not protecting a lead."""
        margin = -s.margin if defending else s.margin
        if not s.end_of_half or s.half_seconds_left > 120:
            return False
        return s.quarter == 2 or margin <= 0

    @staticmethod
    def _should_kneel(s: GameState) -> bool:
        if s.margin <= 0 or s.in_overtime:
            return False
        if s.quarter == 2 and s.half_seconds_left <= 30 and s.ball_on < 60:
            return True
        if s.quarter != 4:
            return False
        snaps_left = 4 - s.down + 1
        burn = snaps_left * 40 - s.timeouts[s.defense] * 38
        return burn >= s.game_seconds_left

    def _fourth_down(self, s: GameState, offense: SimTeam, in_range: bool,
                     rng: random.Random) -> PlayCall:
        late = s.quarter >= 4 and s.game_seconds_left <= 300
        if late and s.margin < 0:
            # A field goal only helps if it ties or wins.
            if in_range and s.margin >= -3 and (s.game_seconds_left <= 120 or s.distance > 4):
                return PlayCall.named("field_goal")
            return self._scrimmage(s, offense, rng)
        level = offense.plan.level("fourth_down")
        if level == 0:
            go = ((s.distance <= 1 and s.ball_on >= 45)
                  or (s.distance <= 2 and 60 <= s.ball_on < 70)
                  or (s.distance <= 3 and s.ball_on >= 97))
        elif level > 0:  # (one more yard, and from five yards further back, per level)
            go = ((s.distance <= 1 + level and s.ball_on >= 45 - 5 * level)
                  or (s.distance <= 2 + level and 60 <= s.ball_on < 70)
                  or (s.distance <= 3 + level and s.ball_on >= 97 - 2 * level))
        else:  # (only a yard or less, from deep in the other team's end)
            go = s.distance <= 1 and s.ball_on >= (60 if level == -1 else 80)
        if go and not (in_range and s.distance > 1 and s.ball_on < 97):
            return self._scrimmage(s, offense, rng)
        if in_range and s.ball_on >= 55:
            return PlayCall.named("field_goal")
        return PlayCall.named("punt")

    def _scrimmage(self, s: GameState, offense: SimTeam, rng: random.Random) -> PlayCall:
        plan = offense.plan
        pass_prob = self._pass_probability(s, offense)
        if rng.random() < pass_prob:
            depth = self._pass_depth(s, rng, plan.level("deep_shots"))
            play_action = s.down <= 2 and rng.random() < scaled(
                0.2, PLAY_ACTION_STEP, plan.level("play_action"))
            # (a plan without this play-action concept runs the straight drop-back)
            return PlayCall.named(pick(AI_PASSES[(depth, play_action)], plan.offense, rng)
                                  or pick(AI_PASSES[(depth, False)], plan.offense, rng))
        short = s.distance <= 2 or s.ball_on >= 95
        inside = rng.random() < (0.75 if short else 0.58)
        return PlayCall.named(pick(AI_RUNS["inside" if inside else "outside"], plan.offense, rng))

    def _pass_probability(self, s: GameState, offense: SimTeam) -> float:
        if s.down == 1:
            p = 0.50
        elif s.down == 2:
            p = 0.64 if s.distance >= 7 else 0.40 if s.distance <= 3 else 0.55
        else:
            p = 0.86 if s.distance >= 5 else 0.36 if s.distance <= 2 else 0.68
        if self._hurry(s):
            p = max(p, 0.86)
        elif s.quarter >= 3 and s.margin <= -9:
            p += 0.18
        elif s.quarter == 4 and s.margin >= 9:
            p -= 0.25
        if s.ball_on >= 97:
            p -= 0.15
        p += 0.04 * offense.pass_lean
        if level := offense.plan.level("pass_rate"):
            p += PASS_RATE_STEP * level
        return min(0.95, max(0.12, p))

    @staticmethod
    def _pass_depth(s: GameState, rng: random.Random, deep_level: int = 0) -> PassDepth:
        to_goal = 100 - s.ball_on
        if to_goal <= 10:
            options, weights = ("short", "medium", "screen"), (0.65, 0.25, 0.10)
        elif s.distance >= 15:
            options, weights = ("deep", "medium", "short"), (0.35, 0.45, 0.20)
        elif s.distance >= 7:
            options, weights = ("deep", "medium", "short", "screen"), (0.18, 0.42, 0.30, 0.10)
        elif s.distance <= 3:
            options, weights = ("short", "medium", "deep", "screen"), (0.62, 0.22, 0.10, 0.06)
        else:
            options, weights = ("deep", "medium", "short", "screen"), (0.14, 0.34, 0.40, 0.12)
        if deep_level and "deep" in options:
            weights = tuple(scaled(w, DEEP_STEP, deep_level) if o == "deep" else w
                            for o, w in zip(options, weights, strict=True))
        return rng.choices(options, weights)[0]
