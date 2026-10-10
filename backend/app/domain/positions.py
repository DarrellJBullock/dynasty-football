"""Positions, position groups, and roster construction rules."""

from enum import StrEnum


class Position(StrEnum):
    QB = "QB"
    RB = "RB"
    FB = "FB"
    WR = "WR"
    TE = "TE"
    OT = "OT"
    OG = "OG"
    C = "C"
    DE = "DE"
    DT = "DT"
    OLB = "OLB"
    MLB = "MLB"
    CB = "CB"
    FS = "FS"
    SS = "SS"
    K = "K"
    P = "P"


class PositionGroup(StrEnum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    OL = "OL"
    DL = "DL"
    LB = "LB"
    DB = "DB"
    ST = "ST"


POSITION_GROUPS: dict[Position, PositionGroup] = {
    Position.QB: PositionGroup.QB,
    Position.RB: PositionGroup.RB,
    Position.FB: PositionGroup.RB,
    Position.WR: PositionGroup.WR,
    Position.TE: PositionGroup.TE,
    Position.OT: PositionGroup.OL,
    Position.OG: PositionGroup.OL,
    Position.C: PositionGroup.OL,
    Position.DE: PositionGroup.DL,
    Position.DT: PositionGroup.DL,
    Position.OLB: PositionGroup.LB,
    Position.MLB: PositionGroup.LB,
    Position.CB: PositionGroup.DB,
    Position.FS: PositionGroup.DB,
    Position.SS: PositionGroup.DB,
    Position.K: PositionGroup.ST,
    Position.P: PositionGroup.ST,
}

OFFENSE = {Position.QB, Position.RB, Position.FB, Position.WR, Position.TE,
           Position.OT, Position.OG, Position.C}
DEFENSE = {Position.DE, Position.DT, Position.OLB, Position.MLB,
           Position.CB, Position.FS, Position.SS}
SPECIAL_TEAMS = {Position.K, Position.P}

ROSTER_MAX = 53

# How many players at each position a generated 53-man roster carries.
ROSTER_TEMPLATE: dict[Position, int] = {
    Position.QB: 3, Position.RB: 4, Position.FB: 1, Position.WR: 6, Position.TE: 3,
    Position.OT: 4, Position.OG: 4, Position.C: 2,
    Position.DE: 4, Position.DT: 4, Position.OLB: 4, Position.MLB: 2,
    Position.CB: 6, Position.FS: 2, Position.SS: 2,
    Position.K: 1, Position.P: 1,
}

# Base starting lineup (11 offense / 11 defense / 2 specialists) used for team ratings
# until a user-editable depth chart exists.
STARTERS: dict[Position, int] = {
    Position.QB: 1, Position.RB: 1, Position.WR: 3, Position.TE: 1,
    Position.OT: 2, Position.OG: 2, Position.C: 1,
    Position.DE: 2, Position.DT: 2, Position.OLB: 2, Position.MLB: 1,
    Position.CB: 2, Position.FS: 1, Position.SS: 1,
    Position.K: 1, Position.P: 1,
}

assert sum(ROSTER_TEMPLATE.values()) == ROSTER_MAX

# Conventional jersey numbers by position (first range preferred).
JERSEY_RANGES: dict[Position, list[range]] = {
    Position.QB: [range(1, 20)], Position.RB: [range(20, 50)], Position.FB: [range(30, 50)],
    Position.WR: [range(10, 20), range(80, 90)], Position.TE: [range(80, 90), range(40, 50)],
    Position.OT: [range(60, 80)], Position.OG: [range(60, 80)], Position.C: [range(50, 80)],
    Position.DE: [range(90, 100), range(50, 60)], Position.DT: [range(90, 100), range(60, 80)],
    Position.OLB: [range(40, 60)], Position.MLB: [range(40, 60)],
    Position.CB: [range(20, 40)], Position.FS: [range(20, 50)], Position.SS: [range(20, 50)],
    Position.K: [range(1, 20)], Position.P: [range(1, 20)],
}


def group_of(position: str) -> PositionGroup:
    return POSITION_GROUPS[Position(position)]


def available_jersey(position: str, taken: set[int]) -> int:
    """Lowest conventional number for the position not already taken (any free number as
    a fallback)."""
    for number_range in JERSEY_RANGES[Position(position)]:
        for number in number_range:
            if number not in taken:
                return number
    for number in range(100):
        if number not in taken:
            return number
    raise ValueError("no jersey numbers available")
