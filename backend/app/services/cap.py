"""The salary cap: which season's cap a move counts against, and dead money.

A team's payroll for a cap year is the cap hits (salaries) of its active contracts plus
the dead money charged to that year.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.contracts import dead_money
from app.models import Contract, DeadMoney, Player, Season


def cap_year(season: Season) -> int:
    """Moves count against this season's cap, or next season's once it's over."""
    return season.year + 1 if season.phase == "offseason" else season.year


def dead_money_totals(db: Session, team_ids: Iterable[int], year: int) -> dict[int, int]:
    ids = list(team_ids)
    totals: dict[int, int] = defaultdict(int)
    if ids:
        for team_id, amount in db.execute(
                select(DeadMoney.team_id, func.sum(DeadMoney.amount))
                .where(DeadMoney.team_id.in_(ids), DeadMoney.year == year)
                .group_by(DeadMoney.team_id)):
            totals[team_id] = int(amount)
    return totals


def dead_money_for(db: Session, team_id: int, year: int) -> int:
    return dead_money_totals(db, [team_id], year)[team_id]


def release_cost(contract: Contract | None, year: int) -> int:
    """Dead money that letting him go now would leave on the `year` cap."""
    if contract is None:
        return 0
    return dead_money(contract.signing_bonus, contract.years, contract.end_year, year)


def charge(db: Session, player: Player, contract: Contract | None, year: int,
           reason: str) -> int:
    """Accelerate the rest of `contract`'s bonus onto its team's `year` cap."""
    amount = release_cost(contract, year)
    if amount > 0:
        db.add(DeadMoney(team_id=contract.team_id, player_id=player.id, year=year,
                         amount=amount, reason=reason))
    return amount
