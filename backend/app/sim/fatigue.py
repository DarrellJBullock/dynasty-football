"""Fatigue: players' energy over a game, the substitutions it brings, and what a tired
player loses. Pure and deterministic (no random draws). Design:
docs/design/depth-and-unity.md §3.

- Energy runs from 100 (fresh) down. Each snap on the field costs a base by position,
  longer plays more, scaled by stamina; each snap off it recovers some, and so do changes
  of possession, timeouts, quarter breaks and halftime. It's kept on the `SimTeam` for
  the game (`team.energy`, missing = fresh) and every game starts fresh.
- A player who drops below his team's sub-out line rests (the next healthy player on the
  depth chart who isn't resting takes his place) until he's back above the sub-in line.
  Quarterbacks, linemen and kickers never come out for fatigue; with no fresher backup,
  the tired play on.
- A tired player's physical ratings drop a point for every few points of energy lost, and
  his injury odds rise a little (`injury_factor`).
"""

import dataclasses
from collections.abc import Iterable, Sequence

from app.domain.positions import Position as P
from app.sim.teams import HURT_ATTRIBUTES, SimPlayer, SimTeam, replacement
from app.sim.tuning import Tuning

# The depth-chart slots that rotate for fatigue.
ROTATING = frozenset({P.RB, P.FB, P.WR, P.TE, P.DE, P.DT, P.OLB, P.MLB, P.CB, P.FS, P.SS})
FRESH = 100.0


def energy(team: SimTeam, player_id: int) -> float:
    return team.energy.get(player_id, FRESH)


def sub_out_line(team: SimTeam, t: Tuning) -> float:
    """Below this a player rests; a team that rotates more (the plan's Rotation) subs out
    sooner."""
    return t.fatigue_sub_out + t.fatigue_rotation_step * team.plan.level("rotation")


def tired(team: SimTeam, player: SimPlayer, t: Tuning) -> SimPlayer:
    """The player as he plays now: his physical ratings down with his energy."""
    drop = int((FRESH - energy(team, player.id)) / t.fatigue_points_per_rating)
    if drop <= 0 or player.id <= 0:
        return player
    key = (player.id, drop)
    copy = team.tired_copies.get(key)
    if copy is None:
        ratings = {k: max(0, v - drop) if k in HURT_ATTRIBUTES else v
                   for k, v in player.ratings.items()}
        copy = team.tired_copies[key] = dataclasses.replace(player, ratings=ratings)
    return copy


def take(team: SimTeam, slot: P, count: int, used: Iterable[int], t: Tuning) -> list[SimPlayer]:
    """The players at a slot for this snap: the first `count` healthy ones on the depth
    chart who aren't resting (or, at rotating slots short of rested players, the tired in
    depth order; stand-ins only when nobody's left), each as tired as he is."""
    if slot not in ROTATING:
        return [tired(team, p, t) for p in team.at(slot, count, used)]
    skip = team.sidelined.union(used)
    healthy = [p for p in team.depth.get(slot, []) if p.id not in skip]
    chosen = [p for p in healthy if p.id not in team.resting][:count]
    if len(chosen) < count:
        tired_out = [p for p in healthy if p.id in team.resting][:count - len(chosen)]
        order = {p.id: i for i, p in enumerate(healthy)}
        chosen = sorted([*chosen, *tired_out], key=lambda p: order[p.id])
    while len(chosen) < count:
        chosen.append(replacement(slot, len(chosen)))
    return [tired(team, p, t) for p in chosen]


def _set(team: SimTeam, player_id: int, value: float, sub_out: float, t: Tuning) -> None:
    if value >= FRESH:
        team.energy.pop(player_id, None)
    else:
        team.energy[player_id] = value
    if value < sub_out:
        team.resting.add(player_id)
    elif value >= t.fatigue_sub_in:
        team.resting.discard(player_id)


def after_snap(team: SimTeam, on_field: Sequence[int], seconds: int, t: Tuning) -> None:
    """The snap's cost for the players on the field, and a breather for the rest."""
    sub_out = sub_out_line(team, t)
    field = set(on_field)
    for player_id in list(team.energy):
        if player_id not in field:
            _set(team, player_id, team.energy[player_id] + t.fatigue_recover_snap, sub_out, t)
    length = seconds / t.fatigue_typical_snap
    for player_id in field:
        player = team.players.get(player_id)
        if player is None:  # a stand-in
            continue
        stamina = player.ratings.get("stamina", 70)
        cost = (t.fatigue_cost.get(player.position, 2.0) * length
                * max(0.4, t.fatigue_stamina_base - stamina / 100))
        _set(team, player_id, energy(team, player_id) - cost, sub_out, t)


def recover(team: SimTeam, amount: float, t: Tuning) -> None:
    """Everyone gets a breather (a change of possession, a timeout, a break)."""
    sub_out = sub_out_line(team, t)
    for player_id in list(team.energy):
        _set(team, player_id, team.energy[player_id] + amount, sub_out, t)


def report(team: SimTeam, limit: int = 6) -> list[dict]:
    """The team's most tired players still in the game (for Coach Mode), most tired first."""
    tired_out = sorted((value, pid) for pid, value in team.energy.items()
                       if pid not in team.sidelined and pid in team.players)[:limit]
    return [{"player_id": pid, "name": team.players[pid].name,
             "position": team.players[pid].position, "team": team.abbreviation,
             "energy": int(value), "resting": pid in team.resting}
            for value, pid in tired_out]


def injury_factor(team: SimTeam, player_id: int, t: Tuning) -> float:
    """How much more likely a tired player is to get hurt."""
    return 1 + t.fatigue_injury_k * (FRESH - energy(team, player_id)) / FRESH
