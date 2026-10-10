"""Box scores folded from play events, so stats can never disagree with the play log.

Plays whose result is a penalty count only the penalty: the underlying action was
nullified (holding) or replaced by the foul (pass interference).
"""

from collections import defaultdict
from dataclasses import dataclass, field, fields

from app.sim.engine import GameResult, PlayRecord
from app.sim.state import Side, other


@dataclass
class PlayerLine:
    pass_att: int = 0
    pass_cmp: int = 0
    pass_yds: int = 0
    pass_td: int = 0
    pass_int: int = 0
    sacked: int = 0
    sack_yds_lost: int = 0
    rush_att: int = 0
    rush_yds: int = 0
    rush_td: int = 0
    rush_long: int = 0
    targets: int = 0
    receptions: int = 0
    rec_yds: int = 0
    rec_td: int = 0
    rec_long: int = 0
    fumbles: int = 0
    fumbles_lost: int = 0
    tackles: int = 0
    sacks: int = 0
    interceptions: int = 0
    int_return_yds: int = 0
    passes_defended: int = 0
    forced_fumbles: int = 0
    fg_att: int = 0
    fg_made: int = 0
    fg_long: int = 0
    xp_att: int = 0
    xp_made: int = 0
    punts: int = 0
    punt_yds: int = 0
    penalties: int = 0

    def as_dict(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}


@dataclass
class TeamLine:
    points: int = 0
    plays: int = 0
    total_yds: int = 0
    pass_yds: int = 0  # net of sacks
    rush_yds: int = 0
    pass_att: int = 0
    pass_cmp: int = 0
    rush_att: int = 0
    first_downs: int = 0
    third_down_att: int = 0
    third_down_conv: int = 0
    turnovers: int = 0
    sacks_allowed: int = 0
    penalties: int = 0
    penalty_yds: int = 0
    punts: int = 0
    fg_att: int = 0
    fg_made: int = 0
    time_of_possession: int = 0  # seconds


@dataclass
class BoxScore:
    players: dict[int, PlayerLine] = field(default_factory=lambda: defaultdict(PlayerLine))
    teams: dict[Side, TeamLine] = field(default_factory=lambda: {"home": TeamLine(),
                                                                 "away": TeamLine()})
    player_team: dict[int, Side] = field(default_factory=dict)


def box_score(game: GameResult) -> BoxScore:
    box = BoxScore()
    box.teams["home"].points = game.home_score
    box.teams["away"].points = game.away_score
    for play in game.plays:
        _fold(box, play)
    # Replacement stand-ins (negative ids) are never credited.
    for pid in [pid for pid in box.players if pid < 0]:
        del box.players[pid]
    return box


def _fold(box: BoxScore, play: PlayRecord) -> None:
    off, deff = play.side, other(play.side)
    team = box.teams[off]
    team.time_of_possession += play.elapsed if play.down is not None else 0
    result = play.result
    is_penalty = result.get("type") == "penalty"

    def p(pid: int, side: Side) -> PlayerLine:
        box.player_team.setdefault(pid, side)
        return box.players[pid]

    if play.down is not None and result.get("type") in ("run", "pass", "sack", "scramble"):
        team.plays += 1
        if play.down == 3:
            team.third_down_att += 1
            if result.get("first_down") or result.get("touchdown"):
                team.third_down_conv += 1
    if result.get("first_down") or (result.get("touchdown") and play.down is not None):
        team.first_downs += 1
    if result.get("turnover"):
        team.turnovers += 1

    for e in play.events:
        t = e["t"]
        if t == "penalty":
            penalized = box.teams[off] if e["team"] == play.offense else box.teams[deff]
            penalized.penalties += 1
            penalized.penalty_yds += e["yards"]
            if "player" in e:
                p(e["player"], off if e["team"] == play.offense else deff).penalties += 1
            continue
        if is_penalty:
            continue
        if t == "rush" or t == "scramble":
            pid = e["player"] if t == "rush" else e["qb"]
            line = p(pid, off)
            line.rush_att += 1
            line.rush_yds += e["yards"]
            line.rush_long = max(line.rush_long, e["yards"])
            team.rush_att += 1
            team.rush_yds += e["yards"]
            team.total_yds += e["yards"]
            if result.get("touchdown"):
                line.rush_td += 1
        elif t == "kneel":
            line = p(e["qb"], off)
            line.rush_att += 1
            line.rush_yds += e["yards"]
            team.rush_att += 1
            team.rush_yds += e["yards"]
            team.total_yds += e["yards"]
        elif t == "sack":
            qb = p(e["qb"], off)
            qb.sacked += 1
            qb.sack_yds_lost += -e["yards"]
            p(e["by"], deff).sacks += 1
            p(e["by"], deff).tackles += 1
            team.sacks_allowed += 1
            team.pass_yds += e["yards"]
            team.total_yds += e["yards"]
        elif t == "pass":
            qb = p(e["qb"], off)
            qb.pass_att += 1
            team.pass_att += 1
            if e["target"] is not None:
                p(e["target"], off).targets += 1
            if e["result"] == "complete":
                receiver = p(e["target"], off)
                qb.pass_cmp += 1
                qb.pass_yds += e["yards"]
                receiver.receptions += 1
                receiver.rec_yds += e["yards"]
                receiver.rec_long = max(receiver.rec_long, e["yards"])
                team.pass_cmp += 1
                team.pass_yds += e["yards"]
                team.total_yds += e["yards"]
                if result.get("touchdown"):
                    qb.pass_td += 1
                    receiver.rec_td += 1
            elif e["result"] == "interception":
                qb.pass_int += 1
        elif t == "interception":
            line = p(e["by"], deff)
            line.interceptions += 1
            line.int_return_yds += e["return"]
        elif t == "pass_defended":
            p(e["by"], deff).passes_defended += 1
        elif t == "tackle":
            for pid in e["by"]:
                p(pid, deff).tackles += 1
        elif t == "fumble":
            p(e["player"], off).fumbles += 1
            p(e["forced_by"], deff).forced_fumbles += 1
            if e["lost"]:
                p(e["player"], off).fumbles_lost += 1
        elif t == "field_goal":
            kicker = p(e["kicker"], off)
            kicker.fg_att += 1
            team.fg_att += 1
            if e["good"]:
                kicker.fg_made += 1
                kicker.fg_long = max(kicker.fg_long, e["distance"])
                team.fg_made += 1
        elif t == "extra_point":
            kicker = p(e["kicker"], off)
            kicker.xp_att += 1
            kicker.xp_made += int(e["good"])
        elif t == "punt":
            punter = p(e["punter"], off)
            punter.punts += 1
            punter.punt_yds += e["yards"]
            team.punts += 1
