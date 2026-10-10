"""Contract valuation rules."""

from app.domain.positions import Position

MIN_SALARY = 750_000

SALARY_POSITION_MULTIPLIER: dict[Position, float] = {
    Position.QB: 1.6, Position.WR: 1.15, Position.OT: 1.15, Position.DE: 1.15,
    Position.CB: 1.15, Position.FB: 0.6, Position.K: 0.4, Position.P: 0.4,
}


def market_salary(position: Position, overall: int) -> int:
    """Expected yearly salary for a player, rounded to $10k. Grows steeply above 55 OVR."""
    above = max(0, overall - 55)
    raw = MIN_SALARY + 2100 * above**2.6 * SALARY_POSITION_MULTIPLIER.get(position, 1.0)
    return int(round(raw, -4))
