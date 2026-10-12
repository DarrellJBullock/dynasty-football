"""Coach Mode in the engine (docs/design/coach-mode.md §3): a game the user coaches is the
engine replayed from the kickoff with the user's calls so far.

`ScriptedCoach` answers each snap from the recorded calls. When it runs out it stops the
game with `NeedCall`, reporting the situation for the next decision; the caller stores
the user's answer and replays one play further. The engine is deterministic, so every
replay reaches the same point. With `autopilot`, the AI calls the rest of the game.
"""

import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from app.sim.engine import GameResult, PlayRecord, _Game
from app.sim.gameplan import GamePlan
from app.sim.playbook import DEFENSE_BY_KEY, OFFENSE_BY_KEY
from app.sim.playcalls import AICoach, DefenseCall, Package, PlayCall
from app.sim.state import GameState, Side, other
from app.sim.teams import SimTeam
from app.sim.tuning import DEFAULT_TUNING

Role = Literal["offense", "defense", "kickoff", "conversion", "audible"]
CHOICES: dict[str, tuple[str, ...]] = {
    "kickoff": ("normal", "squib", "onside"),
    "conversion": ("kick", "two"),
}
CHOICE_NAMES = {"normal": "Kick it deep", "squib": "Squib kick", "onside": "Onside kick",
                "kick": "Extra point", "two": "Go for two"}


@dataclass(frozen=True)
class CoachCall:
    """One of the user's calls: a named offensive play or defensive call, the defense's
    personnel package (None: fit the situation), and whether to call a timeout first; or a
    kicking decision (a kickoff's kind, or a conversion's)."""
    role: Role
    play: str
    package: Package | None = None
    timeout: bool = False
    # At the line (with audibles in the plan): "keep", or the audible switched to.
    audible: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CoachCall":
        return cls(**data)


@dataclass(frozen=True)
class Situation:
    """The snap the user is calling."""
    role: Role
    quarter: int
    clock: int  # seconds left in the period, before any runoff
    clock_running: bool  # time will run off before the snap unless a timeout is called
    possession: Side
    down: int
    distance: int
    ball_on: int  # yards from the offense's own goal line
    score: dict[str, int]
    timeouts: dict[str, int]
    suggestion: str  # the AI's call: an offensive play or defensive call key
    suggested_package: Package | None  # with the AI's personnel, on defense
    # At the line (role "audible"): the call made, what the other side shows, and the
    # audibles from the plan ("keep" snaps the call as made).
    audible_for: Literal["offense", "defense"] | None = None
    called: str | None = None
    look: dict | None = None
    audibles: tuple[str, ...] = ()


class OutOfStep(Exception):  # noqa: N818
    """The recorded calls don't fit the game (it was coached on an older engine)."""


class NeedCall(Exception):  # noqa: N818 (a signal, not an error)
    def __init__(self, situation: Situation):
        super().__init__("the coach needs a call")
        self.situation = situation


class ScriptedCoach:
    """Calls one side's plays from the user's recorded calls."""

    def __init__(self, calls: list[CoachCall], autopilot: bool = False,
                 plans: Mapping[str, GamePlan] | None = None):
        self.calls = calls
        self.used = 0
        self.pending: CoachCall | None = None
        self.autopilot = autopilot
        self.plans = dict(plans or {})
        self.ai = AICoach(plans)  # (its suggestions and autopilot follow the game plan)

    def huddle(self, state: GameState, role: Role, clock_running: bool, offense: SimTeam,
               defense: SimTeam, rng: random.Random) -> None:
        if self.pending and self.pending.role != role:
            self.pending = None  # the period ended before the snap; possession changed
        if self.pending:
            return  # the period ended before the snap: the call carries over
        if self.used < len(self.calls):
            call = self.calls[self.used]
            if call.role != role:
                raise OutOfStep(f"recorded call {self.used} is for the {call.role}, "
                                f"but this snap needs the {role}")
            self.used += 1
            self.pending = call
            return
        if self.autopilot:
            return
        # Ask the AI what it would call, without disturbing the game's random draws.
        copy = random.Random()
        copy.setstate(rng.getstate())
        if role == "offense":
            suggestion = self.ai.offense(state, offense, defense, copy)
            package = None
        else:
            dcall = self.ai.defense(state, offense, defense, copy)
            suggestion, package = dcall, dcall.package
        raise NeedCall(Situation(
            role=role, quarter=state.quarter, clock=state.clock, clock_running=clock_running,
            possession=state.possession, down=state.down, distance=state.distance,
            ball_on=state.ball_on, score=dict(state.score), timeouts=dict(state.timeouts),
            suggestion=suggestion.play or "", suggested_package=package))

    def snap_done(self) -> None:
        self.pending = None

    def audible(self, state: GameState, role: str, team_side: str, look: dict) -> str | None:
        """At the line, for the user's side of the snap: the audible recorded with the call,
        or stop and ask (when the plan has audibles; otherwise the call stands)."""
        if not self.pending or self.pending.role != role:
            return None
        plan = self.plans.get(team_side)
        audibles = plan.audibles(role) if plan else ()
        if not audibles:
            return None
        if self.pending.audible is not None:
            return None if self.pending.audible == "keep" else self.pending.audible
        raise NeedCall(Situation(
            role="audible", quarter=state.quarter, clock=state.clock, clock_running=False,
            possession=state.possession, down=state.down, distance=state.distance,
            ball_on=state.ball_on, score=dict(state.score), timeouts=dict(state.timeouts),
            suggestion="keep", suggested_package=None, audible_for=role,  # type: ignore[arg-type]
            called=self.pending.play, look=look, audibles=audibles))

    def _decide(self, role: Role, state: GameState, suggestion: str) -> str:
        """A kicking decision, made between snaps."""
        if self.used < len(self.calls):
            call = self.calls[self.used]
            if call.role != role:
                raise OutOfStep(f"recorded call {self.used} is for the {call.role}, "
                                f"but the game needs a {role} decision")
            self.used += 1
            return call.play
        if self.autopilot:
            return suggestion
        raise NeedCall(Situation(
            role=role, quarter=state.quarter, clock=state.clock, clock_running=False,
            possession=state.possession, down=state.down, distance=state.distance,
            ball_on=state.ball_on, score=dict(state.score), timeouts=dict(state.timeouts),
            suggestion=suggestion, suggested_package=None))

    def kickoff_call(self, state: GameState, side: str) -> str:
        return self._decide("kickoff", state, self.ai.kickoff_call(state, side))

    def conversion_call(self, state: GameState, side: str) -> str:
        return self._decide("conversion", state, self.ai.conversion_call(state, side))

    def timeout(self, state: GameState, side: str) -> bool:
        if self.pending:
            return self.pending.timeout
        return self.ai.timeout(state, side)

    def offense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> PlayCall:
        if self.pending:
            return PlayCall.named(self.pending.play)
        return self.ai.offense(state, offense, defense, rng)

    def defense(self, state: GameState, offense: SimTeam, defense: SimTeam,
                rng: random.Random) -> DefenseCall:
        if self.pending:
            return DefenseCall.named(self.pending.play,
                                     self.pending.package or AICoach.package(state))
        return self.ai.defense(state, offense, defense, rng)


@dataclass
class CoachedReplay:
    plays: list[PlayRecord]
    situation: Situation | None  # None: the game is over
    result: GameResult | None  # the finished game


def replay(home: SimTeam, away: SimTeam, seed: int, side: Side, calls: list[CoachCall], *,
           autopilot: bool = False, playoff: bool = False, neutral: bool = False) -> CoachedReplay:
    """Play the game from the kickoff with the user coaching `side`, up to the next call
    the user needs to make (or to the final whistle)."""
    plans = {"home": home.plan, "away": away.plan}
    coach = ScriptedCoach(calls, autopilot, plans)
    game = _Game(home, away, seed, playoff, {side: coach, other(side): AICoach(plans)},
                 DEFAULT_TUNING, neutral)
    try:
        result = game.run()
    except NeedCall as need:
        return CoachedReplay(game.plays, need.situation, None)
    return CoachedReplay(result.plays, None, result)


def check_call(call: CoachCall, situation: Situation) -> str | None:
    """Why `call` can't be made in `situation`, or None if it can."""
    if situation.role == "audible":
        if call.role != "audible":
            return "You're at the line: keep the call or audible."
        if call.play != "keep" and call.play not in situation.audibles:
            return f"Audible to one of: {', '.join(situation.audibles)} (or keep the call)."
        if call.package or call.timeout:
            return "At the line it's only the play: no personnel or timeouts."
        return None
    if call.role != situation.role:
        if situation.role in CHOICES:
            return f"This is a {situation.role} decision."
        return f"It's your {situation.role}'s call."
    if call.role in CHOICES:
        if call.play not in CHOICES[call.role]:
            return f"Choose one of: {', '.join(CHOICES[call.role])}."
        if call.package or call.timeout:
            return "That's a kicking decision: no personnel or timeouts."
        return None
    known = OFFENSE_BY_KEY if call.role == "offense" else DEFENSE_BY_KEY
    if call.play not in known:
        return f"Unknown {call.role} play: {call.play}."
    if call.package and call.role == "offense":
        return "Personnel packages are a defensive choice."
    if call.timeout:
        mine = situation.possession if call.role == "offense" else other(situation.possession)
        if situation.timeouts[mine] <= 0:
            return "You have no timeouts left."
        if not situation.clock_running:
            return "The clock is already stopped."
    return None
