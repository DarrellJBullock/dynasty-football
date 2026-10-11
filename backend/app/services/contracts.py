"""Re-signing: the franchise negotiates with its expiring players once the season ends.

The window opens in the offseason (after the champion is crowned) and closes when the
next season starts; anyone not re-signed by then leaves in free agency (AI teams re-sign
automatically, see services/offseason.py). A new deal starts next season.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import preferred_years, required_salary
from app.domain.positions import Position
from app.models import Contract, DeadMoney, Player, Season, Team
from app.schemas import (
    ContractTerms,
    DeadMoneyOut,
    ExpiringContract,
    NegotiationResult,
    ReSignOffer,
    TeamContracts,
)
from app.services import cap
from app.services.errors import RosterError
from app.services.season import season_view
from app.services.serializers import contract_out, player_summary
from app.services.teams import current_season, load_roster, payroll


def window_open(season: Season) -> bool:
    return season.phase == "offseason"


def is_expiring(player: Player, season: Season) -> bool:
    contract = player.active_contract
    return contract is not None and contract.end_year <= season.year


def re_signed(player: Player, season: Season) -> bool:
    """Signed an extension this offseason (a new deal replacing one that just ended)."""
    contract = player.active_contract
    return (contract is not None and contract.start_year == season.year + 1
            and any(not c.is_active and c.team_id == contract.team_id
                    and c.end_year == season.year for c in player.contracts))


def next_year_payroll(roster: list[Player], season: Season) -> int:
    """Salary already committed to next season."""
    return sum(c.salary for p in roster
               if (c := p.active_contract) is not None and c.end_year > season.year)


def asking(player: Player) -> ContractTerms:
    years = preferred_years(player.age)
    return ContractTerms(years=years, salary=required_salary(
        Position(player.position), player.overall, player.age, years))


def contracts_view(db: Session, team: Team) -> TeamContracts:
    season = _season(db, team)
    roster = load_roster(db, team.id)
    expiring = [p for p in roster if is_expiring(p, season)
                or (window_open(season) and re_signed(p, season))]
    expiring.sort(key=lambda p: (-p.overall, p.id))
    signed = sorted((p for p in roster if p.active_contract is not None),
                    key=lambda p: (-p.active_contract.salary, p.id))
    dead = db.scalars(select(DeadMoney).where(DeadMoney.team_id == team.id,
                                              DeadMoney.year >= season.year)
                      .order_by(DeadMoney.year, DeadMoney.amount.desc())).all()
    dead_by_year: dict[int, int] = defaultdict(int)
    for charge in dead:
        dead_by_year[charge.year] += charge.amount
    return TeamContracts(
        season=season_view(db, season),
        window_open=window_open(season),
        salary_cap=team.league.salary_cap,
        payroll=payroll(roster) + dead_by_year[season.year],
        next_year_payroll=next_year_payroll(roster, season) + dead_by_year[season.year + 1],
        dead_money=[DeadMoneyOut(player_id=c.player_id, name=c.player.full_name,
                                 position=c.player.position, year=c.year, amount=c.amount,
                                 reason=c.reason) for c in dead],
        expiring=[ExpiringContract(
            player=player_summary(p), asking=asking(p),
            re_signed=contract_out(p.active_contract) if re_signed(p, season) else None)
            for p in expiring],
        players=[player_summary(p) for p in signed],
    )


def negotiate(db: Session, player: Player, offer: ReSignOffer) -> NegotiationResult:
    """Offer an expiring player a new deal. He signs if the salary meets his price for
    that length (more for lengths he doesn't want); otherwise he names his price."""
    if player.team_id is None:
        raise RosterError("player is not on a team")
    team = db.get(Team, player.team_id)
    season = _season(db, team)
    if not window_open(season):
        raise RosterError("Re-signing opens when the season is over.")
    if re_signed(player, season):
        raise RosterError(f"{player.full_name} has already re-signed.")
    if not is_expiring(player, season):
        raise RosterError(f"{player.full_name} isn't in the final year of his contract.")

    needed = required_salary(Position(player.position), player.overall, player.age,
                             offer.years)
    if offer.salary < needed:
        counter = ContractTerms(salary=needed, years=offer.years)
        return NegotiationResult(
            accepted=False, counter=counter, player=player_summary(player),
            message=f"{player.full_name} wants at least {_money(needed)} a year "
                    f"for {_years(offer.years)}.")

    roster = load_roster(db, team.id)
    committed = next_year_payroll(roster, season) + cap.dead_money_for(db, team.id,
                                                                       season.year + 1)
    if committed + offer.salary > team.league.salary_cap:
        raise RosterError("That deal would put next season's payroll over the cap.")
    player.active_contract.is_active = False
    player.contracts.append(Contract.signed(team.id, season.year + 1, offer.years,
                                            offer.salary))
    db.flush()
    return NegotiationResult(
        accepted=True, counter=None, player=player_summary(player),
        message=f"{player.full_name} signs for {_years(offer.years)} at "
                f"{_money(offer.salary)} a year.")


def _season(db: Session, team: Team) -> Season:
    season = current_season(db, team.league_id)
    if season is None:
        raise RosterError("league has no active season", 400)
    return season


def _money(dollars: int) -> str:
    return f"${dollars / 1_000_000:.2f}M".replace(".00M", "M")


def _years(years: int) -> str:
    return f"{years} year{'s' if years != 1 else ''}"
