"""Game loop: kickoffs, snaps, clock, scoring, overtime.

    result = simulate_game(home, away, seed=123)

Deterministic: the same teams, seed, and tuning always produce the same game.
"""

import random
from dataclasses import dataclass, field

from app.domain.positions import Position as P
from app.sim import resolve as rs
from app.sim.playcalls import AICoach, Coach, PlayCall, field_goal_distance
from app.sim.state import OT_SECONDS, QUARTER_SECONDS, GameState, Side, other
from app.sim.teams import SimTeam
from app.sim.text import describe
from app.sim.tuning import DEFAULT_TUNING, Tuning

SIM_VERSION = "1.0"
MAX_PLAYS = 400  # safety valve; real games have ~130-180 records


@dataclass
class PlayRecord:
    n: int
    quarter: int
    clock: str
    offense: str  # team abbreviation with the ball (the kicking team on kickoffs)
    side: Side
    down: int | None
    distance: int | None
    ball_on: int | None  # offense perspective
    call: dict | None
    defense: dict | None
    result: dict
    events: list[dict]
    elapsed: int  # game seconds consumed, including pre-snap runoff
    score: dict[str, int]  # after the play, keyed "home"/"away"
    text: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class GameResult:
    home: SimTeam
    away: SimTeam
    seed: int
    home_score: int
    away_score: int
    overtime: bool
    playoff: bool
    plays: list[PlayRecord] = field(default_factory=list)
    sim_version: str = SIM_VERSION

    @property
    def winner(self) -> SimTeam | None:
        if self.home_score == self.away_score:
            return None
        return self.home if self.home_score > self.away_score else self.away


def simulate_game(home: SimTeam, away: SimTeam, seed: int, *, playoff: bool = False,
                  neutral: bool = False, coaches: dict[Side, Coach] | None = None,
                  tuning: Tuning = DEFAULT_TUNING) -> GameResult:
    """`playoff`: overtime continues until there's a winner. `neutral`: no home edge
    ("home" is just the designated side, e.g. the higher seed in a championship)."""
    return _Game(home, away, seed, playoff, coaches, tuning, neutral).run()


class _Game:
    def __init__(self, home: SimTeam, away: SimTeam, seed: int, playoff: bool,
                 coaches: dict[Side, Coach] | None, tuning: Tuning, neutral: bool = False):
        self.teams: dict[Side, SimTeam] = {"home": home, "away": away}
        self.neutral = neutral
        self.seed = seed
        self.playoff = playoff
        self.rng = random.Random(seed)
        ai = AICoach()
        self.coaches: dict[Side, Coach] = coaches or {"home": ai, "away": ai}
        self.t = tuning
        self.s = GameState()
        self.plays: list[PlayRecord] = []
        self.clock_running = False
        self.over = False
        self.sudden_death = False
        self.warned_halves: set[int] = set()
        self.pending_elapsed = 0
        self.warning_during_play = False
        self.names = {pid: p.name for team in self.teams.values()
                      for pid, p in team.players.items()}

    # ---------- top level ----------

    def run(self) -> GameResult:
        receiver: Side = self.rng.choice(["home", "away"])
        self.s.second_half_receiver = other(receiver)
        self.kickoff(kicking=other(receiver))
        while not self.over and len(self.plays) < MAX_PLAYS:
            self.snap()
        s = self.s
        return GameResult(self.teams["home"], self.teams["away"], self.seed, s.score["home"],
                          s.score["away"], s.quarter >= 5, self.playoff, self.plays)

    def edge(self, side: Side) -> float:
        if self.neutral:
            return 0.0
        return self.t.home_edge if side == "home" else -self.t.home_edge

    # ---------- clock ----------

    def tick(self, seconds: int, during_play: bool = False) -> None:
        s = self.s
        before = s.clock
        s.clock = max(0, s.clock - seconds)
        self.pending_elapsed += before - s.clock
        half = 1 if s.quarter <= 2 else 2
        if s.quarter in (2, 4) and half not in self.warned_halves and before > 120 >= s.clock:
            self.warned_halves.add(half)
            if not during_play:
                self.pending_elapsed -= 120 - s.clock
                s.clock = 120
            else:
                self.warning_during_play = True
            self.clock_running = False

    def runoff(self) -> None:
        """Time between snaps while the clock runs."""
        s = self.s
        if AICoach._hurry(s):
            seconds = self.t.runoff_hurry
        elif s.quarter == 4 and s.margin > 0:
            seconds = self.t.runoff_bleed
        else:
            seconds = self.rng.randint(*self.t.runoff)
        self.tick(seconds)

    def maybe_timeout(self) -> None:
        s = self.s
        if not self.clock_running:
            return
        if AICoach._hurry(s) and s.timeouts[s.offense] > 0:
            s.timeouts[s.offense] -= 1
            self.clock_running = False
        elif (s.quarter >= 4 and not s.in_overtime and s.margin > 0
              and s.game_seconds_left <= 180 and s.timeouts[s.defense] > 0):
            s.timeouts[s.defense] -= 1
            self.clock_running = False

    def end_period(self) -> None:
        s = self.s
        self.clock_running = False
        if s.quarter in (1, 3):
            s.quarter += 1
            s.clock = QUARTER_SECONDS
        elif s.quarter == 2:
            s.quarter, s.clock = 3, QUARTER_SECONDS
            s.timeouts = {"home": 3, "away": 3}
            self.kickoff(kicking=other(s.second_half_receiver))
        elif s.quarter == 4:
            if s.score["home"] != s.score["away"]:
                self.over = True
                return
            s.quarter, s.clock = 5, OT_SECONDS
            s.timeouts = {"home": 2, "away": 2}
            s.ot_possessions = 0
            receiver: Side = self.rng.choice(["home", "away"])
            self.kickoff(kicking=other(receiver))
        else:  # overtime period expired
            if self.playoff and s.score["home"] == s.score["away"]:
                s.quarter += 1
                s.clock = OT_SECONDS
                self.sudden_death = True
            else:
                self.over = True

    # ---------- possession & scoring ----------

    def give_ball(self, side: Side, ball_on: int) -> None:
        s = self.s
        if s.in_overtime:
            if (s.ot_possessions == 2 and s.ot_first_score is not None
                    and not self.sudden_death):
                self.over = True  # first team's FG stands; second possession didn't answer
            s.ot_possessions += 1
        s.possession = side
        s.ball_on = max(1, min(99, ball_on))
        s.first_down()

    def score(self, side: Side, points: int, kind: str) -> None:
        s = self.s
        s.score[side] += points
        if self.plays:  # the scoring play was recorded just before; show the new score
            self.plays[-1].score = dict(s.score)
        if not s.in_overtime:
            return
        n = s.ot_possessions
        if kind in ("touchdown", "safety") or n >= 3 or self.sudden_death:
            self.over = True
        elif n == 1:
            s.ot_first_score = side
        elif n == 2:
            if s.ot_first_score is None:
                self.over = True
            else:
                self.sudden_death = True

    def kickoff(self, kicking: Side) -> None:
        if self.over:
            return
        kicker = self.teams[kicking].one(P.K)
        spot, event = rs.resolve_kickoff(kicker, self.rng, self.t)
        before = self.s.clock
        self.clock_running = False
        if not event["touchback"]:
            self.tick(5, during_play=True)
        self.record(kicking, None, None, {"type": "kickoff"}, [event], before, situation=False)
        self.give_ball(other(kicking), spot)

    def touchdown(self, side: Side) -> None:
        s = self.s
        self.score(side, 6, "touchdown")
        if self.over:
            return
        kicker = self.teams[side].one(P.K)
        margin_after = s.score[side] - s.score[other(side)]
        go_for_two = s.quarter == 4 and s.game_seconds_left <= 300 and margin_after in (-2, -5)
        if go_for_two:
            good = self.rng.random() < 0.47
            event = {"t": "two_point", "good": good}
            if good:
                s.score[side] += 2
        else:
            event = rs.resolve_extra_point(kicker, self.rng, self.t)
            if event["good"]:
                s.score[side] += 1
        self.record(side, None, None, {"type": "conversion"}, [event], s.clock, situation=False)
        self.kickoff(kicking=side)

    # ---------- snaps ----------

    def snap(self) -> None:
        s = self.s
        if s.clock <= 0:
            self.end_period()
            return
        self.pending_elapsed = 0
        self.warning_during_play = False
        self.maybe_timeout()
        if self.clock_running:
            self.runoff()
            if s.clock <= 0:
                self.end_period()
                return

        side = s.offense
        offense, defense = self.teams[side], self.teams[s.defense]
        call = self.coaches[side].offense(s, offense, defense, self.rng)
        clock_before = s.clock
        situation = (s.down, s.distance, s.ball_on)

        if call.kind == "punt":
            self.punt(side, call, situation, clock_before)
        elif call.kind == "field_goal":
            self.field_goal(side, call, situation, clock_before)
        elif call.kind == "kneel":
            events = [{"t": "kneel", "qb": offense.one(P.QB).id, "yards": -1}]
            self.tick(2, during_play=True)
            self.advance(side, -1, call, None, {"type": "kneel", "yards": -1}, events,
                         situation, clock_before, clock_stops=False)
        else:
            self.scrimmage(side, call, situation, clock_before)

    def punt(self, side: Side, call: PlayCall, situation, clock_before: int) -> None:
        punter = self.teams[side].one(P.P)
        spot, event = rs.resolve_punt(punter, self.s.ball_on, self.rng, self.t)
        self.tick(8, during_play=True)
        self.clock_running = False
        self.record(side, call, None, {"type": "punt"}, [event], clock_before, situation)
        self.give_ball(other(side), spot)

    def field_goal(self, side: Side, call: PlayCall, situation, clock_before: int) -> None:
        s = self.s
        kicker = self.teams[side].one(P.K)
        distance = field_goal_distance(s.ball_on)
        event = rs.resolve_field_goal(kicker, distance, self.rng, self.t)
        self.tick(5, during_play=True)
        self.clock_running = False
        self.record(side, call, None, {"type": "field_goal", "good": event["good"]}, [event],
                    clock_before, situation)
        if event["good"]:
            self.score(side, 3, "field_goal")
            self.kickoff(kicking=side)
        else:
            self.give_ball(other(side), max(20, 100 - (s.ball_on - 7)))

    def scrimmage(self, side: Side, call: PlayCall, situation, clock_before: int) -> None:
        s = self.s
        t, rng = self.t, self.rng
        offense, defense = self.teams[side], self.teams[s.defense]
        dcall = self.coaches[s.defense].defense(s, offense, defense, rng)
        off = rs.offense_personnel(offense, rng)

        if rng.random() < t.false_start_rate:
            yards = min(5, s.ball_on // 2)
            event = {"t": "penalty", "team": offense.abbreviation, "kind": "false_start",
                     "yards": yards, "player": rng.choice(off.line).id}
            s.ball_on -= yards
            s.distance += yards
            self.clock_running = False
            self.record(side, call, dcall.describe(), {"type": "penalty"}, [event], clock_before,
                        situation)
            return

        deff = rs.defense_personnel(defense, dcall, rng)
        edge = self.edge(side)
        if call.kind == "run":
            outcome = rs.resolve_run(call, dcall, off, deff, s.ball_on, edge, rng, t)
        else:
            obvious = s.down >= 3 and s.distance >= 5
            outcome = rs.resolve_pass(call, dcall, off, deff, s.ball_on, edge, rng, t, obvious)
        rs.maybe_holding(outcome, off, rng, t)
        self.tick(outcome.duration, during_play=True)

        penalty = outcome.penalty
        if penalty:
            events = [*outcome.events, {"t": "penalty", "team": (
                offense if penalty["team"] == "offense" else defense).abbreviation, **penalty}]
            self.clock_running = False
            if penalty["team"] == "offense":
                yards = min(penalty["yards"], s.ball_on // 2)
                events[-1]["yards"] = yards
                s.ball_on -= yards
                s.distance += yards
                self.record(side, call, dcall.describe(), {"type": "penalty"}, events,
                            clock_before, situation, wiped=True)
            else:
                s.ball_on += penalty["yards"]
                self.record(side, call, dcall.describe(),
                            {"type": "penalty", "first_down": True}, events, clock_before,
                            situation)
                if s.ball_on >= 100:
                    s.ball_on = 99
                s.first_down()
            return

        result = {"type": outcome.kind, "yards": outcome.yards}
        if outcome.result:
            result["result"] = outcome.result
        if outcome.turnover:
            self.turnover(side, call, dcall, outcome, situation, clock_before)
            return
        # Out of bounds only stops the clock late in a half (last 2:00 of the 1st half,
        # last 5:00 of the 2nd half and overtime); otherwise it restarts on the snap.
        late = (s.quarter == 2 and s.clock <= 120) or (s.quarter >= 4 and s.clock <= 300)
        stops = outcome.clock_stops or (outcome.out_of_bounds and late)
        self.advance(side, outcome.yards, call, dcall.describe(), result, outcome.events,
                     situation, clock_before, stops)

    def turnover(self, side: Side, call, dcall, outcome: rs.Outcome, situation,
                 clock_before: int) -> None:
        taker = other(side)
        new_ball_on = 100 - outcome.turnover_spot + outcome.return_yards
        result = {"type": outcome.kind, "yards": outcome.yards, "turnover": True}
        if outcome.result:
            result["result"] = outcome.result
        self.clock_running = False
        if new_ball_on >= 100:
            result["defensive_td"] = True
            self.record(side, call, dcall.describe(), result, outcome.events, clock_before,
                        situation)
            self.touchdown(taker)
            return
        self.record(side, call, dcall.describe(), result, outcome.events, clock_before, situation)
        self.give_ball(taker, max(1, new_ball_on))

    def advance(self, side: Side, yards: int, call, dcall: dict | None, result: dict,
                events: list[dict], situation, clock_before: int, clock_stops: bool) -> None:
        s = self.s
        new_spot = s.ball_on + yards
        if new_spot >= 100:
            result["touchdown"] = True
            self.clock_running = False
            self.record(side, call, dcall, result, events, clock_before, situation)
            self.touchdown(side)
            return
        if new_spot <= 0:
            result["safety"] = True
            self.clock_running = False
            self.record(side, call, dcall, result, events, clock_before, situation)
            self.score(other(side), 2, "safety")
            self.kickoff(kicking=side)
            return
        gained_first = yards >= s.distance
        if gained_first:
            result["first_down"] = True
        self.clock_running = not clock_stops and not self.warning_during_play
        self.record(side, call, dcall, result, events, clock_before, situation)
        s.ball_on = new_spot
        if gained_first:
            s.first_down()
            return
        s.down += 1
        s.distance -= yards
        if s.down > 4:
            self.clock_running = False
            self.plays[-1].result["turnover_on_downs"] = True
            self.give_ball(other(side), 100 - s.ball_on)

    # ---------- play log ----------

    def record(self, side: Side, call: PlayCall | None, dcall: dict | None, result: dict,
               events: list[dict], clock_before: int, situation, wiped: bool = False) -> None:
        s = self.s
        down, distance, ball_on = situation if situation else (None, None, None)
        play = PlayRecord(
            n=len(self.plays) + 1, quarter=s.quarter,
            clock=f"{clock_before // 60}:{clock_before % 60:02d}",
            offense=self.teams[side].abbreviation, side=side, down=down, distance=distance,
            ball_on=ball_on, call=call.describe() if call else None, defense=dcall,
            result=result, events=events, elapsed=self.pending_elapsed,
            score=dict(s.score),
        )
        if wiped:
            play.result["nullified"] = True
        play.text = describe(play, self.names, self.teams)
        self.pending_elapsed = 0
        self.plays.append(play)
