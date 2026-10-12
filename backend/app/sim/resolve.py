"""Resolve a single play from the two calls and the players on the field.

Every result is described by `events` (see docs/design/simulation-engine.md §6); stats
and play-by-play text are derived from those events, never computed separately.
"""

import math
import random
from dataclasses import dataclass, field

from app.domain.positions import Position as P
from app.sim.playbook import OFFENSE_BY_KEY, concept_edge
from app.sim.playcalls import DefenseCall, PlayCall
from app.sim.teams import SimPlayer, SimTeam
from app.sim.tuning import Tuning


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def wmean(pairs: list[tuple[float, float]]) -> float:
    """Weighted mean of (value, weight) pairs."""
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else 0.0


# ---------- personnel ----------

@dataclass
class Offense:
    qb: SimPlayer
    rb: SimPlayer
    wrs: list[SimPlayer]
    te: SimPlayer
    tackles: list[SimPlayer]
    guards: list[SimPlayer]
    center: SimPlayer

    @property
    def line(self) -> list[SimPlayer]:
        return [*self.tackles, *self.guards, self.center]

    @property
    def all(self) -> list[SimPlayer]:
        return [self.qb, self.rb, *self.wrs, self.te, *self.line]


@dataclass
class Defense:
    ends: list[SimPlayer]
    tackles: list[SimPlayer]
    olbs: list[SimPlayer]
    mlb: SimPlayer
    corners: list[SimPlayer]
    fs: SimPlayer
    ss: SimPlayer

    @property
    def front(self) -> list[SimPlayer]:
        return [*self.ends, *self.tackles]

    @property
    def backers(self) -> list[SimPlayer]:
        return [*self.olbs, self.mlb]

    @property
    def all(self) -> list[SimPlayer]:
        return [*self.front, *self.backers, *self.corners, self.fs, self.ss]


def offense_personnel(team: SimTeam, rng: random.Random) -> Offense:
    """Base 11 personnel (1 RB, 1 TE, 3 WR); the RB2 spells the starter ~30% of snaps."""
    used: list[int] = []

    def take(slot: P, count: int) -> list[SimPlayer]:
        players = team.at(slot, count, used)
        used.extend(p.id for p in players)
        return players

    qb = take(P.QB, 1)[0]
    rbs = team.at(P.RB, 2, used)
    rb = rbs[1] if rng.random() < 0.3 and rbs[1].id > 0 else rbs[0]
    used.append(rb.id)
    return Offense(qb=qb, rb=rb, wrs=take(P.WR, 3), te=take(P.TE, 1)[0], tackles=take(P.OT, 2),
                   guards=take(P.OG, 2), center=take(P.C, 1)[0])


def defense_personnel(team: SimTeam, call: DefenseCall, rng: random.Random) -> Defense:
    """4-3 base; nickel swaps an OLB for a third CB, dime swaps both. DL rotate ~25%."""
    used: list[int] = []

    def take(slot: P, count: int, rotate: bool = False) -> list[SimPlayer]:
        pool = team.at(slot, count + 1, used)
        chosen = pool[:count]
        if rotate and pool[count].id > 0 and rng.random() < 0.25:
            chosen[rng.randrange(count)] = pool[count]
        used.extend(p.id for p in chosen)
        return chosen

    ends = take(P.DE, 2, rotate=True)
    tackles = take(P.DT, 2, rotate=True)
    olb_count = {"base": 2, "nickel": 1, "dime": 0}[call.package]
    cb_count = {"base": 2, "nickel": 3, "dime": 4}[call.package]
    olbs = take(P.OLB, olb_count) if olb_count else []
    return Defense(ends=ends, tackles=tackles, olbs=olbs, mlb=take(P.MLB, 1)[0],
                   corners=take(P.CB, cb_count), fs=take(P.FS, 1)[0], ss=take(P.SS, 1)[0])


BASE_DEFENSE = DefenseCall()


def offense_lineup(team: SimTeam) -> list[SimPlayer]:
    """Base 11 personnel's first string, without rotation or random draws."""
    used: list[int] = []

    def take(slot: P, count: int) -> list[SimPlayer]:
        players = team.at(slot, count, used)
        used.extend(p.id for p in players)
        return players

    return [*take(P.QB, 1), *take(P.RB, 1), *take(P.WR, 3), *take(P.TE, 1), *take(P.OT, 2),
            *take(P.OG, 2), *take(P.C, 1)]


def defense_lineup(team: SimTeam, call: DefenseCall) -> list[SimPlayer]:
    """The package's first-string defenders, without rotation or random draws (for plays
    where the ball isn't snapped)."""
    used: list[int] = []

    def take(slot: P, count: int) -> list[SimPlayer]:
        players = team.at(slot, count, used)
        used.extend(p.id for p in players)
        return players

    olbs = {"base": 2, "nickel": 1, "dime": 0}[call.package]
    corners = {"base": 2, "nickel": 3, "dime": 4}[call.package]
    return [*take(P.DE, 2), *take(P.DT, 2), *(take(P.OLB, olbs) if olbs else []),
            *take(P.MLB, 1), *take(P.CB, corners), *take(P.FS, 1), *take(P.SS, 1)]


# ---------- outcomes ----------

@dataclass
class Outcome:
    kind: str  # run | pass | sack | scramble | kneel
    yards: int = 0  # gain from the line of scrimmage, offense perspective
    events: list[dict] = field(default_factory=list)
    result: str = ""  # pass: complete | incomplete | interception | throwaway
    clock_stops: bool = False  # incompletions, turnovers, scores
    out_of_bounds: bool = False  # stops the clock only late in a half (engine decides)
    duration: int = 6  # seconds the snap itself takes
    turnover: bool = False  # defense gets the ball
    turnover_spot: int = 0  # offense-perspective ball_on where the turnover happened
    return_yards: int = 0  # defense's return, toward the offense's goal
    penalty: dict | None = None  # {"team": "offense"|"defense", "kind", "yards", ...}


def _tackle(rng: random.Random, candidates: list[tuple[SimPlayer, float]]) -> dict:
    players = [p for p, _ in candidates]
    weights = [w * (1 + max(-0.5, p.r("tackling")) * 0.3) for p, w in candidates]
    tackler = rng.choices(players, weights)[0]
    return {"t": "tackle", "by": [tackler.id]}


def resolve_run(call: PlayCall, dcall: DefenseCall, off: Offense, deff: Defense, ball_on: int,
                edge: float, rng: random.Random, t: Tuning) -> Outcome:
    carrier = off.rb
    inside = call.direction != "outside"

    def block(p: SimPlayer) -> float:
        return 0.65 * p.r("run_blocking") + 0.35 * p.r("strength")

    def shed(p: SimPlayer) -> float:
        return 0.6 * p.r("block_shedding") + 0.2 * p.r("strength") + 0.2 * p.r("play_recognition")

    if inside:
        blockers = [(block(p), 1.0) for p in [*off.guards, off.center]]
        blockers += [(block(p), 0.5) for p in off.tackles] + [(block(off.te), 0.3)]
        front = [(shed(p), 1.0) for p in deff.tackles] + [(shed(p), 0.5) for p in deff.ends]
        front += [(shed(deff.mlb), 0.8)] + [(shed(p), 0.4) for p in deff.olbs]
        burst = 0.35 * carrier.r("ball_carrier_vision") + 0.25 * carrier.r("strength") \
            + 0.2 * carrier.r("acceleration") + 0.2 * carrier.r("elusiveness")
    else:
        blockers = [(block(p), 1.0) for p in off.tackles] + [(block(off.te), 0.9)]
        blockers += [(block(p), 0.4) for p in off.guards]
        front = [(shed(p), 1.0) for p in deff.ends] + [(shed(p), 0.8) for p in deff.olbs]
        front += [(shed(p), 0.35) for p in deff.tackles] + [(shed(deff.corners[0]), 0.3)]
        burst = 0.3 * carrier.r("speed") + 0.25 * carrier.r("elusiveness") \
            + 0.25 * carrier.r("ball_carrier_vision") + 0.2 * carrier.r("acceleration")

    pursuit = wmean([(p.r("tackling") * 0.6 + p.r("speed") * 0.4, 1.0)
                     for p in [*deff.backers, deff.ss, deff.fs]])
    push = wmean(blockers) - wmean(front) + edge
    to_goal = 100 - ball_on
    goal_line = t.red_zone_run * max(0.0, 1 - to_goal / 10)  # stacked box near the goal
    concept = t.concept_run_k * concept_edge(t.concept_edges, call.play, dcall.shell)
    mu = (t.run_mu + t.run_push_k * push + t.run_carrier_k * (burst - 0.5 * pursuit)
          + t.run_light_box[dcall.package] - (0.6 if dcall.blitz else 0.0) - goal_line
          + concept)
    yards = max(-5, round(rng.gauss(mu, t.run_sd)))
    breakaway = False
    if yards >= 4:
        speed = (carrier.r("speed") + carrier.r("elusiveness")) / 2
        if rng.random() < sigmoid(t.breakaway_base + t.breakaway_k * (speed - pursuit)):
            yards += round(rng.expovariate(1 / t.breakaway_mean))
            breakaway = True
    yards = min(yards, 100 - ball_on)

    events: list[dict] = [{"t": "handoff", "to": carrier.id,
                           "direction": call.direction or "inside"}]
    events.append({"t": "rush", "player": carrier.id, "yards": yards})
    if ball_on + yards >= 100:
        return Outcome("run", yards, events, clock_stops=True, duration=6)

    candidates = ([(p, 3.0) for p in deff.backers] + [(p, 2.0) for p in deff.front]
                  if yards <= 3 and not breakaway else
                  [(p, 2.5) for p in deff.backers] + [(deff.ss, 2.0), (deff.fs, 1.5)]
                  + [(p, 1.0) for p in deff.corners])
    tackle = _tackle(rng, candidates)
    events.append(tackle)

    fumble_p = t.fumble_rate * math.exp(-0.45 * carrier.r("carrying"))
    if rng.random() < fumble_p:
        lost = rng.random() < 0.5
        events.append({"t": "fumble", "player": carrier.id, "forced_by": tackle["by"][0],
                       "lost": lost})
        if lost:
            return Outcome("run", yards, events, clock_stops=True, turnover=True,
                           turnover_spot=ball_on + yards, duration=6)

    out_of_bounds = not inside and rng.random() < 0.3
    return Outcome("run", yards, events, out_of_bounds=out_of_bounds, duration=6)


def _coverage_matchups(off: Offense, deff: Defense, blitzer: SimPlayer | None
                       ) -> list[tuple[SimPlayer, SimPlayer, float]]:
    """(receiver, primary defender, base target weight index) for each eligible receiver."""
    available = [p for p in [*deff.corners, deff.ss, deff.fs, *deff.backers]
                 if blitzer is None or p.id != blitzer.id]
    corners = [p for p in deff.corners if p in available]
    others = [p for p in available if p not in corners]

    def pick(pool: list[SimPlayer], fallback: list[SimPlayer]) -> SimPlayer:
        return pool.pop(0) if pool else fallback.pop(0)

    pairs = []
    for wr in off.wrs:
        pairs.append((wr, pick(corners, others)))
    linebackers = [p for p in others if p.position in ("OLB", "MLB")]
    safeties = [p for p in others if p not in linebackers]
    pairs.append((off.te, pick(safeties, linebackers) if safeties or linebackers else deff.fs))
    pairs.append((off.rb, pick(linebackers, safeties) if linebackers or safeties else deff.fs))
    return [(r, d, 0.0) for r, d in pairs]


TARGET_WEIGHTS = {  # WR1, WR2, WR3, TE, RB
    "screen": (2.0, 1.8, 1.0, 1.0, 5.0),
    "short": (3.0, 2.6, 2.0, 2.4, 1.6),
    "medium": (3.4, 2.8, 2.0, 2.0, 0.5),
    "deep": (4.0, 3.0, 1.6, 0.9, 0.1),
}
AIR_YARDS = {"screen": (-3, 2), "short": (2, 8), "medium": (9, 17), "deep": (18, 42)}


def resolve_pass(call: PlayCall, dcall: DefenseCall, off: Offense, deff: Defense, ball_on: int,
                 edge: float, rng: random.Random, t: Tuning,
                 obvious_pass: bool = False) -> Outcome:
    """`obvious_pass` (3rd/4th and 5+): the defense knows a pass is coming, so it plays
    the sticks in coverage and rushes harder."""
    depth = call.depth or "short"
    qb = off.qb
    events: list[dict] = [{"t": "dropback", "qb": qb.id, "depth": depth}]

    # Protection
    blitzer = None
    rushers = list(deff.front)
    if dcall.blitz:
        blitzer = (deff.backers or [deff.ss])[rng.randrange(len(deff.backers) or 1)]
        rushers.append(blitzer)
    protect = [0.75 * p.r("pass_blocking") + 0.25 * p.r("strength") for p in off.line]
    if dcall.blitz:
        protect.append(0.5 * off.rb.r("pass_blocking"))
    rush = [0.7 * p.r("pass_rush") + 0.15 * p.r("speed") + 0.15 * p.r("strength") for p in rushers]
    pressure = (sum(rush) / len(rush) - sum(protect) / len(protect) - edge
                + (t.blitz_bonus if dcall.blitz else 0.0)
                + (t.passing_down_rush if obvious_pass else 0.0))
    depth_hold = {"screen": -1.4, "short": -0.35, "medium": 0.0, "deep": 0.45}[depth]
    play_action = 0.2 if call.play_action else 0.0

    sack_p = sigmoid(t.sack_base + t.sack_k * pressure + depth_hold + play_action
                     - 0.15 * qb.r("awareness"))
    if rng.random() < sack_p:
        if qb.r("speed") > 0.5 and rng.random() < t.scramble_rate:
            gain = min(100 - ball_on, max(-2, round(rng.gauss(5, 4))))
            events.append({"t": "scramble", "qb": qb.id, "yards": gain})
            if ball_on + gain < 100:
                events.append(_tackle(rng, [(p, 1.0) for p in deff.backers or [deff.ss]]))
            return Outcome("scramble", gain, events, duration=6,
                           out_of_bounds=rng.random() < 0.4)
        sacker = rng.choices(rushers, [1 + max(0, p.r("pass_rush")) for p in rushers])[0]
        loss = -min(ball_on - 1, max(2, round(rng.gauss(6.5, 2))))
        events.append({"t": "sack", "qb": qb.id, "by": sacker.id, "yards": loss})
        if rng.random() < 0.08:  # strip sack
            lost = rng.random() < 0.55
            events.append({"t": "fumble", "player": qb.id, "forced_by": sacker.id, "lost": lost})
            if lost:
                return Outcome("sack", loss, events, clock_stops=True, turnover=True,
                               turnover_spot=ball_on + loss, duration=6)
        return Outcome("sack", loss, events, duration=6)

    pressured = rng.random() < sigmoid(t.pressure_base + t.pressure_k * pressure + depth_hold)
    if pressured:
        events.append({"t": "pressure"})

    # Openness for every route, then the QB's read. A named play sets who he looks for,
    # and its concept fares better or worse against the coverage shell.
    deep_help = deff.fs.r("zone_coverage") * 0.3 if depth == "deep" else 0.0
    named = OFFENSE_BY_KEY.get(call.play or "")
    weights = named.targets if named and named.targets else TARGET_WEIGHTS[depth]
    concept = t.concept_pass_k * concept_edge(t.concept_edges, call.play, dcall.shell)
    designed = max(range(len(weights)), key=lambda i: weights[i]) if depth == "screen" else -1
    options = []
    for i, ((receiver, defender, _), weight) in enumerate(
            zip(_coverage_matchups(off, deff, blitzer), weights, strict=True)):
        speed_k = 0.45 if depth == "deep" else 0.3
        route = 0.45 * receiver.r("route_running") + speed_k * receiver.r("speed") \
            + 0.25 * receiver.r("agility")
        if dcall.coverage == "man":
            cover = 0.55 * defender.r("man_coverage") + 0.25 * defender.r("speed") \
                + 0.2 * defender.r("play_recognition")
        else:
            cover = 0.5 * defender.r("zone_coverage") + 0.3 * defender.r("play_recognition") \
                + 0.2 * defender.r("speed")
        sticks = t.passing_down_coverage if obvious_pass else 0.0
        design = t.screen_open if i == designed else 0.0
        openness = (route - cover - deep_help - sticks + concept + design
                    + rng.gauss(0, t.open_sd))
        options.append((receiver, defender, weight, openness))

    order = []
    pool = list(options)
    while pool:  # read order: weighted by the play's design
        choice = rng.choices(pool, [w for _, _, w, _ in pool])[0]
        order.append(choice)
        pool.remove(choice)
    reads = 2 + (qb.r("awareness") > 0) + (not pressured) + (qb.r("awareness") > 1)
    seen = order[:reads]
    # He favors the play's progression: the first read unless someone else is clearly open.
    bonus = {id(o): b for o, b in zip(seen, t.read_bonus, strict=False)}
    target, defender, _, openness = max(
        seen, key=lambda o: o[3] + bonus.get(id(o), 0.0) + rng.gauss(0, 0.25))

    if pressured and openness < -1.1:
        events.append({"t": "pass", "qb": qb.id, "target": None, "result": "throwaway",
                       "air": 0, "yards": 0})
        return Outcome("pass", 0, events, result="throwaway", clock_stops=True, duration=5)

    to_goal = 100 - ball_on
    low, high = AIR_YARDS[depth]
    air = min(rng.randint(low, high), to_goal)
    accuracy = qb.r("throw_accuracy") + (0.35 * qb.r("throw_power") if depth == "deep" else 0)

    int_p = sigmoid(t.interception_base[depth] - t.interception_open_k * openness
                    - 0.35 * accuracy + (0.6 if pressured else 0.0))
    if rng.random() < int_p:
        back = rng.choice([defender, deff.fs, deff.ss, defender])
        ret = round(rng.expovariate(1 / 9))
        events.append({"t": "pass", "qb": qb.id, "target": target.id, "result": "interception",
                       "air": air, "yards": 0})
        events.append({"t": "interception", "by": back.id, "return": ret})
        return Outcome("pass", 0, events, result="interception", clock_stops=True,
                       turnover=True, turnover_spot=ball_on + air, return_yards=ret, duration=6)

    # Red zone: a compressed field leaves less room to get open, and throws that
    # reach the end zone are contested.
    red_zone = t.red_zone_pass * max(0.0, 1 - to_goal / 20)
    end_zone = t.end_zone_throw if air >= to_goal else 0.0
    complete_p = sigmoid(t.completion_base[depth] + t.completion_accuracy_k * accuracy
                         + t.completion_open_k * openness
                         + t.completion_catch_k * target.r("catching")
                         - (t.completion_pressure if pressured else 0.0) + edge
                         - red_zone - end_zone)
    if rng.random() >= complete_p:
        events.append({"t": "pass", "qb": qb.id, "target": target.id, "result": "incomplete",
                       "air": air, "yards": 0})
        if rng.random() < 0.45:
            events.append({"t": "pass_defended", "by": defender.id})
        penalty = None
        if depth in ("medium", "deep") and rng.random() < t.pass_interference_rate:
            spot_gain = max(1, min(air, to_goal - 1))
            penalty = {"team": "defense", "kind": "pass_interference", "yards": spot_gain,
                       "player": defender.id, "automatic_first": True}
        return Outcome("pass", 0, events, result="incomplete", clock_stops=True, duration=5,
                       penalty=penalty)

    yac = 0
    if air < to_goal:
        tackler = defender
        yac_mean = t.yac_mean[depth] * math.exp(
            0.25 * (target.r("elusiveness") + target.r("speed")) / 2 - 0.2 * tackler.r("tackling"))
        yac = min(round(rng.expovariate(1 / yac_mean)), to_goal - air)
    gained = air + yac
    events.append({"t": "pass", "qb": qb.id, "target": target.id, "result": "complete",
                   "air": air, "yards": gained})
    if ball_on + gained < 100:
        events.append({"t": "tackle", "by": [defender.id]})
        if rng.random() < t.fumble_rate * 0.6 * math.exp(-0.45 * target.r("carrying")):
            lost = rng.random() < 0.5
            events.append({"t": "fumble", "player": target.id, "forced_by": defender.id,
                           "lost": lost})
            if lost:
                return Outcome("pass", gained, events, result="complete", clock_stops=True,
                               turnover=True, turnover_spot=ball_on + gained, duration=6)
    return Outcome("pass", gained, events, result="complete", duration=6,
                   out_of_bounds=rng.random() < 0.28, clock_stops=ball_on + gained >= 100)


# ---------- special teams ----------

def field_goal_probability(distance: int, kicker: SimPlayer, t: Tuning) -> float:
    power = kicker.r("kick_power") * 0.25 if distance >= 45 else 0.0
    return sigmoid(t.field_goal_base - t.field_goal_k * (distance - 30) / 10
                   + 0.45 * kicker.r("kick_accuracy") + power)


def resolve_field_goal(kicker: SimPlayer, distance: int, rng: random.Random, t: Tuning) -> dict:
    good = rng.random() < field_goal_probability(distance, kicker, t)
    return {"t": "field_goal", "kicker": kicker.id, "distance": distance, "good": good}


def _hands(team: SimTeam) -> float:
    """The hands team's catching: the receivers, tight end and back."""
    players = [*team.at(P.WR, 3), team.one(P.TE), team.one(P.RB)]
    return sum(p.r("catching") for p in players) / len(players)


def resolve_onside(kicker: SimPlayer, kicking: SimTeam, receiving: SimTeam, rng: random.Random,
                   t: Tuning) -> tuple[bool, int, dict]:
    """An onside kick: about 10–13 yards, then a scramble for the ball. Returns (the
    kicking team recovered, the kicking team's yard line where it was recovered, event)."""
    chance = sigmoid(t.onside_base + t.onside_kick_k * kicker.r("kick_accuracy")
                     + t.onside_hands_k * (_hands(kicking) - _hands(receiving)))
    recovered = rng.random() < chance
    spot = 35 + rng.randint(10, 13)
    team = kicking if recovered else receiving
    recoverer = rng.choice([*team.at(P.WR, 3), team.one(P.TE), team.one(P.RB)])
    return recovered, spot, {"t": "kickoff", "kicker": kicker.id, "touchback": False,
                             "return": 100 - spot, "kind": "onside", "recovered": recovered,
                             "recovered_by": recoverer.id}


def resolve_squib(kicker: SimPlayer, rng: random.Random, t: Tuning) -> tuple[int, dict]:
    """A low, bouncing kick the return team can't take back far. Returns (receiving team's
    ball_on, event)."""
    spot = max(15, min(45, round(rng.gauss(t.squib_return_spot, t.squib_sd))))
    return spot, {"t": "kickoff", "kicker": kicker.id, "touchback": False, "return": spot,
                  "kind": "squib"}


def resolve_extra_point(kicker: SimPlayer, rng: random.Random, t: Tuning) -> dict:
    good = rng.random() < field_goal_probability(33, kicker, t)
    return {"t": "extra_point", "kicker": kicker.id, "good": good}


def resolve_punt(punter: SimPlayer, ball_on: int, rng: random.Random, t: Tuning
                 ) -> tuple[int, dict]:
    """Returns (receiving team's ball_on, event)."""
    gross = round(rng.gauss(t.punt_gross + 3 * punter.r("kick_power"), t.punt_sd))
    gross = max(25, gross)
    landing = ball_on + gross
    if landing >= 100:
        return 20, {"t": "punt", "punter": punter.id, "yards": 100 - ball_on,
                    "touchback": True, "return": 0}
    fair = rng.random() < t.punt_fair_catch or landing >= 92
    ret = 0 if fair else min(round(rng.expovariate(1 / t.punt_return_mean)), landing - 1)
    return 100 - landing + ret, {"t": "punt", "punter": punter.id, "yards": gross,
                                 "touchback": False, "fair_catch": fair, "return": ret}


def resolve_kickoff(kicker: SimPlayer, rng: random.Random, t: Tuning) -> tuple[int, dict]:
    """Returns (receiving team's ball_on, event)."""
    if rng.random() < t.kickoff_touchback + 0.05 * kicker.r("kick_power"):
        return 30, {"t": "kickoff", "kicker": kicker.id, "touchback": True, "return": 0}
    spot = max(8, min(60, round(rng.gauss(t.kickoff_return_spot, 7))))
    return spot, {"t": "kickoff", "kicker": kicker.id, "touchback": False, "return": spot}
