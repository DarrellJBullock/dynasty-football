"""Team snapshots for simulation, built once per game from rosters and depth charts.

Pure: works on anything shaped like a player (see PlayerLike below), so the engine never
touches the database.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from statistics import mean
from typing import Protocol

from app.domain.depth_chart import build_chart, is_available
from app.domain.positions import Position
from app.domain.ratings import ATTRIBUTES
from app.sim.gameplan import NEUTRAL, GamePlan, TeamRatings, generated
from app.sim.tuning import DEFAULT_TUNING

REPLACEMENT_RATING = 40  # an empty depth slot plays like a street free agent

# How strongly rating *differences* matter. A rating at RATING_CENTER (a typical starter)
# maps to the same score as before; each point away from it counts RATING_SPREAD as much.
# Without this, small edges compound over ~130 plays and a +5 OVR team wins ~97% of games;
# at 0.32 it wins ~70% (design target 65-75%).
RATING_CENTER = 78
RATING_SPREAD = 0.32


class PlayerLike(Protocol):
    id: int
    first_name: str
    last_name: str
    position: str
    overall: int
    injury_status: str
    injury_count: int


# What a questionable player loses while playing hurt (Tuning.questionable_drop points).
HURT_ATTRIBUTES = ("speed", "acceleration", "agility", "strength")


@dataclass(frozen=True)
class SimPlayer:
    id: int
    name: str  # "K. Quarles" style, for play-by-play text
    position: str
    overall: int
    ratings: Mapping[str, int]
    injuries: int = 0  # career injuries before this game (proneness)

    def r(self, attribute: str) -> float:
        """Rating as a matchup score: 78 → 0.8; each point above or below 78 adds or
        subtracts 0.035 (see RATING_SPREAD)."""
        offset = (self.ratings[attribute] - RATING_CENTER) * RATING_SPREAD
        return (RATING_CENTER - 70 + offset) / 10


def replacement(position: Position, index: int) -> SimPlayer:
    """Stand-in for an unfilled spot. Ids are negative (never credited in stats) and unique
    per slot and depth, so stand-ins at different positions are never confused."""
    slot_number = list(Position).index(position)
    return SimPlayer(id=-(1000 + slot_number * 100 + index), name=f"Reserve {position.value}",
                     position=position.value, overall=REPLACEMENT_RATING,
                     ratings=dict.fromkeys(ATTRIBUTES, REPLACEMENT_RATING))


@dataclass
class SimTeam:
    id: int
    abbreviation: str
    name: str
    # Players in depth-chart order for every slot.
    depth: dict[Position, list[SimPlayer]]
    players: dict[int, SimPlayer] = field(default_factory=dict)
    # Out / IR going into the game (refreshed between weeks), and hurt during this game.
    unavailable: set[int] = field(default_factory=set)
    injured: set[int] = field(default_factory=set)
    sidelined: set[int] = field(default_factory=set)  # both of the above
    # Fatigue (sim/fatigue.py): energy below 100 by player id (missing: fresh), who is
    # resting until he recovers, and tired copies of players by (id, points lost).
    energy: dict[int, float] = field(default_factory=dict)
    resting: set[int] = field(default_factory=set)
    tired_copies: dict[tuple[int, int], "SimPlayer"] = field(default_factory=dict)
    plan: GamePlan = NEUTRAL  # which plays and calls the AI makes for this team, and how

    def start_game(self) -> None:
        """Reset in-game state; called by the engine at kickoff."""
        self.injured = set()
        self.sidelined = set(self.unavailable)
        self.energy = {}
        self.resting = set()
        self.__dict__.pop("pass_lean", None)

    def injure(self, player_id: int) -> None:
        self.injured.add(player_id)
        self.sidelined.add(player_id)

    def at(self, slot: Position, count: int, skip: Iterable[int] = ()) -> list[SimPlayer]:
        """Top `count` players at a slot, skipping ids already on the field and anyone out
        or hurt; replacement players fill any shortfall so a play can always be run."""
        used = self.sidelined.union(skip)
        chosen = [p for p in self.depth.get(slot, []) if p.id not in used][:count]
        while len(chosen) < count:
            chosen.append(replacement(slot, len(chosen)))
        return chosen

    def one(self, slot: Position, depth_index: int = 0, skip: Iterable[int] = ()) -> SimPlayer:
        return self.at(slot, depth_index + 1, skip)[depth_index]

    @cached_property
    def pass_lean(self) -> float:
        """Positive when the passing game is stronger than the running game (in tens of OVR);
        the AI leans its run/pass mix toward the team's strength."""
        passing = mean([self.one(Position.QB).overall,
                        *(p.overall for p in self.at(Position.WR, 3)),
                        self.one(Position.TE).overall])
        running = mean([self.one(Position.RB).overall,
                        *(p.overall for p in self.at(Position.OT, 2)),
                        *(p.overall for p in self.at(Position.OG, 2)),
                        self.one(Position.C).overall])
        return (passing - running) / 10


def short_name(first: str, last: str) -> str:
    return f"{first[:1]}. {last}" if first else last


def build_sim_team(
    team_id: int,
    abbreviation: str,
    name: str,
    roster: Sequence[PlayerLike],
    ratings: Mapping[int, Mapping[str, int]],
    overrides: Mapping[Position, Sequence[int]] | None = None,
    plan: GamePlan | None = None,
) -> SimTeam:
    """Snapshot a roster: depth-chart order per slot (custom orders honoured, cross-listed
    players included); unavailable (Out/IR) players are skipped when picking lineups, and
    questionable ones play hurt (`playing_hurt`). The game plan is the team's saved one,
    or else one drawn from its roster's strengths."""
    chart = build_chart(roster, overrides or {})
    sim_players = {
        p.id: SimPlayer(id=p.id, name=short_name(p.first_name, p.last_name),
                        position=p.position, overall=p.overall,
                        ratings=(playing_hurt(ratings[p.id]) if p.injury_status == "questionable"
                                 else dict(ratings[p.id])),
                        injuries=p.injury_count or 0)
        for p in roster
    }
    depth = {slot: [sim_players[p.id] for p in players] for slot, players in chart.items()}
    team = SimTeam(id=team_id, abbreviation=abbreviation, name=name, depth=depth,
                   players=sim_players,
                   unavailable={p.id for p in roster if not is_available(p)})
    team.start_game()
    team.plan = plan if plan is not None else generated(plan_ratings(team))
    return team


def playing_hurt(ratings: Mapping[str, int]) -> dict[str, int]:
    """A questionable player's ratings for the game: slower and weaker than when healthy."""
    drop = DEFAULT_TUNING.questionable_drop
    return {k: max(0, v - drop) if k in HURT_ATTRIBUTES else v for k, v in ratings.items()}


def plan_ratings(team: SimTeam) -> TeamRatings:
    """The starters' numbers a generated game plan leans on."""
    def avg(slot: Position, count: int, rating: str) -> float:
        return mean(p.ratings.get(rating, 50) for p in team.at(slot, count))
    return TeamRatings(
        arm_and_speed=mean([avg(Position.QB, 1, "throw_power"), avg(Position.WR, 2, "speed")]),
        pass_rush=mean([avg(Position.DE, 2, "pass_rush"), avg(Position.OLB, 2, "pass_rush")]),
        man_coverage=avg(Position.CB, 2, "man_coverage"),
        depth=mean(p.overall for slot, starters in ((Position.RB, 1), (Position.DE, 2),
                                                    (Position.DT, 2), (Position.CB, 2))
                   for p in team.at(slot, starters + 1)[starters:]))


def team_to_dict(team: SimTeam) -> dict:
    """A JSON-safe snapshot of a team going into a game (rosters, depth, who's out), so a
    game can be replayed later exactly as it started, whatever has changed since."""
    return {
        "id": team.id, "abbreviation": team.abbreviation, "name": team.name,
        "players": [{"id": p.id, "name": p.name, "position": p.position, "overall": p.overall,
                     "ratings": dict(p.ratings), "injuries": p.injuries}
                    for p in team.players.values()],
        "depth": {slot.value: [p.id for p in players] for slot, players in team.depth.items()},
        "unavailable": sorted(team.unavailable),
        "plan": team.plan.to_dict(),
    }


def team_from_dict(data: dict) -> SimTeam:
    players = {p["id"]: SimPlayer(id=p["id"], name=p["name"], position=p["position"],
                                  overall=p["overall"], ratings=p["ratings"],
                                  injuries=p.get("injuries", 0))
               for p in data["players"]}
    depth = {Position(slot): [players[pid] for pid in ids] for slot, ids in data["depth"].items()}
    team = SimTeam(id=data["id"], abbreviation=data["abbreviation"], name=data["name"],
                   depth=depth, players=players, unavailable=set(data["unavailable"]),
                   # (snapshots from before game plans played the whole book, neutrally)
                   plan=GamePlan.from_dict(data.get("plan")))
    team.start_game()
    return team
