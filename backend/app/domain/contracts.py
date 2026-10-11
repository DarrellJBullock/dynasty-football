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


MAX_CONTRACT_YEARS = 5
LENGTH_PREMIUM = 0.05  # extra salary per year away from the player's preferred length


def preferred_years(age: int) -> int:
    """Young players want long-term security; veterans want short deals."""
    if age <= 26:
        return 4
    if age <= 29:
        return 3
    if age <= 31:
        return 2
    return 1


def required_salary(position: Position, overall: int, age: int, years: int) -> int:
    """The salary a player needs to sign for `years`: market value, plus a premium for
    each year away from the length he prefers. Rounded to $10k."""
    gap = abs(years - preferred_years(age))
    raw = market_salary(position, overall) * (1 + LENGTH_PREMIUM * gap)
    return max(MIN_SALARY, int(round(raw, -4)))
