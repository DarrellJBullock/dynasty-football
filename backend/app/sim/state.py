"""Game state: clock, possession, field position, score."""

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["home", "away"]

QUARTER_SECONDS = 15 * 60
OT_SECONDS = 10 * 60
TIMEOUTS_PER_HALF = 3


def other(side: Side) -> Side:
    return "away" if side == "home" else "home"


@dataclass
class GameState:
    quarter: int = 1  # 5+ = overtime
    clock: int = QUARTER_SECONDS  # seconds left in the period
    possession: Side = "away"
    # Yards from the offense's own goal line (0-100): 75 = opponent's 25.
    ball_on: int = 25
    down: int = 1
    distance: int = 10
    score: dict[Side, int] = field(default_factory=lambda: {"home": 0, "away": 0})
    timeouts: dict[Side, int] = field(default_factory=lambda: {"home": 3, "away": 3})
    two_minute_warning_used: bool = False
    # Who receives the second-half kickoff (the team that kicked first).
    second_half_receiver: Side = "home"
    # Overtime bookkeeping (modified sudden death).
    ot_possessions: int = 0
    ot_first_score: Side | None = None

    @property
    def offense(self) -> Side:
        return self.possession

    @property
    def defense(self) -> Side:
        return other(self.possession)

    @property
    def margin(self) -> int:
        """Offense score minus defense score."""
        return self.score[self.offense] - self.score[self.defense]

    @property
    def in_overtime(self) -> bool:
        return self.quarter >= 5

    @property
    def half_seconds_left(self) -> int:
        """Seconds until halftime (Q1/Q2) or the end of regulation (Q3/Q4)."""
        if self.quarter in (1, 3):
            return self.clock + QUARTER_SECONDS
        return self.clock

    @property
    def game_seconds_left(self) -> int:
        if self.in_overtime:
            return self.clock
        return self.clock + (4 - self.quarter) * QUARTER_SECONDS

    @property
    def end_of_half(self) -> bool:
        return self.quarter in (2, 4) or self.in_overtime

    def first_down(self) -> None:
        self.down = 1
        self.distance = min(10, 100 - self.ball_on)

    def change_possession(self, ball_on: int) -> None:
        """Hand the ball to the defense at `ball_on` measured from the NEW offense's goal."""
        self.possession = other(self.possession)
        self.ball_on = max(1, min(99, ball_on))
        self.first_down()

    def clock_label(self) -> str:
        minutes, seconds = divmod(max(0, self.clock), 60)
        return f"{minutes}:{seconds:02d}"
