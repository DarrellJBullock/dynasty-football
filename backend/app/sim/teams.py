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


@dataclass(frozen=True)
class SimPlayer:
    id: int
    name: str  # "K. Quarles" style, for play-by-play text
    position: str
    overall: int
    ratings: Mapping[str, int]

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
    # Available players in depth-chart order for every slot.
    depth: dict[Position, list[SimPlayer]]
    players: dict[int, SimPlayer] = field(default_factory=dict)

    def at(self, slot: Position, count: int, skip: Iterable[int] = ()) -> list[SimPlayer]:
        """Top `count` players at a slot, skipping ids already on the field; replacement
        players fill any shortfall so a play can always be run."""
        used = set(skip)
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
) -> SimTeam:
    """Snapshot a roster: depth-chart order per slot (custom orders honoured, cross-listed
    players included), unavailable (Out/IR) players removed."""
    chart = build_chart(roster, overrides or {})
    sim_players = {
        p.id: SimPlayer(id=p.id, name=short_name(p.first_name, p.last_name),
                        position=p.position, overall=p.overall, ratings=dict(ratings[p.id]))
        for p in roster
    }
    depth = {slot: [sim_players[p.id] for p in players if is_available(p)]
             for slot, players in chart.items()}
    return SimTeam(id=team_id, abbreviation=abbreviation, name=name, depth=depth,
                   players=sim_players)
