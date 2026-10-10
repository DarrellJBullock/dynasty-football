"""Depth chart persistence: read the effective chart, save or reset slot orders."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain.depth_chart import SLOTS, build_chart, starter_count, starting_lineup, unit_of
from app.domain.positions import Position
from app.models import DepthChartEntry, Player, Team
from app.schemas import DepthChart, DepthSlot
from app.services.errors import RosterError
from app.services.serializers import player_summary
from app.services.teams import load_overrides, load_roster, team_detail


def read_depth_chart(db: Session, team: Team) -> DepthChart:
    roster = load_roster(db, team.id)
    overrides = load_overrides(db, [team.id])[team.id]
    chart = build_chart(roster, overrides)
    lineup = starting_lineup(chart)
    slots = [
        DepthSlot(
            slot=slot,
            unit=unit_of(slot),
            starters=starter_count(slot),
            customized=slot in overrides,
            starter_ids=[p.id for p in lineup[slot]],
            players=[player_summary(p) for p in chart[slot]],
        )
        for slot in SLOTS
    ]
    return DepthChart(team=team_detail(team, roster, overrides), slots=slots)


def set_slot(db: Session, team: Team, slot: Position, player_ids: list[int]) -> None:
    if len(set(player_ids)) != len(player_ids):
        raise RosterError("a player can only be listed once per slot", 422)
    roster_ids = {p.id for p in load_roster(db, team.id)}
    strangers = [pid for pid in player_ids if pid not in roster_ids]
    if strangers:
        raise RosterError(f"players not on this roster: {', '.join(map(str, strangers))}", 422)

    reset_slot(db, team, slot)
    db.add_all(
        DepthChartEntry(team_id=team.id, slot=slot.value, depth=depth, player_id=pid)
        for depth, pid in enumerate(player_ids, start=1)
    )
    db.flush()


def reset_slot(db: Session, team: Team, slot: Position) -> None:
    db.execute(delete(DepthChartEntry).where(DepthChartEntry.team_id == team.id,
                                             DepthChartEntry.slot == slot.value))
    db.flush()


def reset_all(db: Session, team: Team) -> None:
    db.execute(delete(DepthChartEntry).where(DepthChartEntry.team_id == team.id))
    db.flush()


def remove_player(db: Session, player: Player, slot: Position | None = None) -> None:
    """Drop a player from saved orders (every slot, or just one); others keep their order."""
    stmt = delete(DepthChartEntry).where(DepthChartEntry.player_id == player.id)
    if slot is not None:
        stmt = stmt.where(DepthChartEntry.slot == slot.value)
    db.execute(stmt)
    db.flush()
