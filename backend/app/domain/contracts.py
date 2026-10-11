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


BONUS_SHARE = 0.3  # of a deal's total value, paid up front as a (guaranteed) signing bonus


def signing_bonus(salary: int, years: int) -> int:
    """The bonus in a deal paying `salary` a year (its cap hit) for `years`. Minimum deals
    carry none."""
    if salary <= MIN_SALARY or years <= 0:
        return 0
    return int(round(BONUS_SHARE * salary * years, -4))


def dead_money(bonus: int, years: int, end_year: int, cap_year: int) -> int:
    """What releasing (or trading) a player leaves on the cap in `cap_year`: the bonus
    proration for every season from `cap_year` to the end of his deal."""
    remaining = max(0, min(years, end_year - cap_year + 1))
    return int(round(bonus * remaining / years)) if years else 0
