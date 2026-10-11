"""Free agency: a five-day market between the year rollover and the preseason.

The new season opens in phase "free_agency" (services/offseason.advance). Each market day:

1. AI teams bid for the positions they lost this offseason (log["lost"]), spreading their
   cap room over the spots still open, plus one clear upgrade a day (a free agent well
   above their best player at his position). The franchise makes its own offers.
2. When the day is played, free agents (best first) take their best offer if it meets
   their asking for the day (domain/free_agency.DEMAND); otherwise they wait.
3. Unsigned AI offers are replaced by fresh bids for the next day.

After the last day the market closes: any spot a team still lost is filled with an
undrafted rookie (placeholder until the draft) and the season moves to the preseason.
Deterministic per league, year, and day.
"""

import hashlib
import random
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.domain.contracts import MIN_SALARY, preferred_years, required_salary
from app.domain.free_agency import MARKET_DAYS, Bid, acceptable, demand, ranked
from app.domain.positions import ROSTER_MAX, Position, available_jersey
from app.models import Franchise, FreeAgentOffer, League, Player, Season, Team
from app.schemas import (
    ContractTerms,
    FreeAgencyOut,
    FreeAgentRow,
    MarketSigning,
)
from app.services.errors import RosterError
from app.services.offseason import (
    FREE_AGENT_FLOOR,
    ROSTER_SPOT_RESERVE,
    _rookie,
    _sign,
)
from app.services.season import season_view
from app.services.serializers import player_summary, team_summary
from app.services.teams import (
    current_season,
    load_overrides,
    team_lineup,
    team_ratings,
)

AI_SALARY_RANGE = (0.9, 1.12)  # AI offers, as a share of the player's price
AI_CHOICES = (3, 2, 1)  # weights for an AI team's top three affordable targets
UPGRADE_MARGIN = 4  # an AI team also chases a free agent this much better than its starter


def market_rng(league_id: int, year: int, day: int) -> random.Random:
    digest = hashlib.sha256(f"free-agency:{league_id}:{year}:{day}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def franchise_team_id(db: Session, league_id: int) -> int | None:
    return db.scalar(select(Franchise.team_id).where(Franchise.league_id == league_id))


def price(player: Player, years: int) -> int:
    return required_salary(Position(player.position), player.overall, player.age, years)


def asking(player: Player) -> ContractTerms:
    years = preferred_years(player.age)
    return ContractTerms(salary=price(player, years), years=years)


class _Market:
    """Rosters, payrolls, the pool, and team strength, loaded once per step."""

    def __init__(self, db: Session, season: Season):
        self.db = db
        self.season = season
        self.league: League = season.league
        self.log: dict = season.offseason_log or {}
        self.teams = list(db.scalars(select(Team).where(Team.league_id == self.league.id)
                                     .order_by(Team.id)))
        players = db.scalars(
            select(Player).where(Player.league_id == self.league.id,
                                 Player.retired_year.is_(None))
            .options(selectinload(Player.ratings), selectinload(Player.contracts))
            .order_by(Player.overall.desc(), Player.id))
        self.rosters: dict[int, list[Player]] = defaultdict(list)
        self.pool: list[Player] = []
        for player in players:
            (self.rosters[player.team_id] if player.team_id else self.pool).append(player)
        self.payrolls = {t.id: sum(c.salary for p in self.rosters[t.id]
                                   if (c := p.active_contract)) for t in self.teams}
        self.user_team = franchise_team_id(db, self.league.id)
        self.departed_from = {e["player"]: e["team"] for e in self.log.get("departed", [])}

    def lost(self, team_id: int) -> list[str]:
        return self.log.setdefault("lost", {}).setdefault(str(team_id), [])

    def strength(self) -> dict[int, int]:
        overrides = load_overrides(self.db, [t.id for t in self.teams])
        return {t.id: team_ratings(team_lineup(self.rosters[t.id], overrides[t.id])).overall
                for t in self.teams}

    def fits(self, team_id: int, salary: int) -> bool:
        return (len(self.rosters[team_id]) < ROSTER_MAX
                and self.payrolls[team_id] + salary <= self.league.salary_cap)

    def sign(self, player: Player, team: Team, salary: int, years: int) -> None:
        roster = self.rosters[team.id]
        taken = {p.jersey_number for p in roster}
        if player.jersey_number in taken:
            player.jersey_number = available_jersey(player.position, taken)
        player.team_id = team.id
        _sign(player, team, self.season.year, salary, years)
        roster.append(player)
        self.pool.remove(player)
        self.payrolls[team.id] += salary
        lost = self.lost(team.id)
        if player.position in lost:
            lost.remove(player.position)

    def save_log(self) -> None:
        self.season.offseason_log = self.log
        flag_modified(self.season, "offseason_log")


def _require_market(season: Season) -> None:
    if season.phase != "free_agency":
        raise RosterError("Free agency isn't open.")


def open_market(db: Session, season: Season) -> None:
    """Called when the new season opens: AI teams make their day-one bids."""
    _ai_offers(db, _Market(db, season))


def _ai_offers(db: Session, market: _Market) -> None:
    season = market.season
    db.execute(delete(FreeAgentOffer).where(
        FreeAgentOffer.season_id == season.id, FreeAgentOffer.status == "pending",
        FreeAgentOffer.team_id != (market.user_team or 0)))
    rng = market_rng(market.league.id, season.year, season.free_agency_day)
    by_position: dict[str, list[Player]] = defaultdict(list)
    for player in market.pool:
        if player.overall >= FREE_AGENT_FLOOR:
            by_position[player.position].append(player)
    teams = [t for t in market.teams if t.id != market.user_team]
    rng.shuffle(teams)
    for team in teams:
        open_spots = ROSTER_MAX - len(market.rosters[team.id])
        budget = market.league.salary_cap - market.payrolls[team.id]
        targeted: set[int] = set()

        # One clear upgrade a day: the free agent who most outclasses this team's best
        # player at his position (the spot it lost elsewhere goes to a rookie).
        if open_spots > 0:
            starters: dict[str, int] = {}
            for player in market.rosters[team.id]:
                starters[player.position] = max(starters.get(player.position, 0), player.overall)
            reserve = (open_spots - 1) * ROSTER_SPOT_RESERVE
            upgrades = []
            for candidate in market.pool:
                gain = candidate.overall - starters.get(candidate.position, 0)
                if (gain >= UPGRADE_MARGIN and candidate.overall >= FREE_AGENT_FLOOR
                        and market.departed_from.get(candidate.id) != team.id):
                    years = preferred_years(candidate.age)
                    salary = int(round(price(candidate, years) * rng.uniform(*AI_SALARY_RANGE),
                                       -4))
                    if salary + reserve <= budget:
                        upgrades.append((gain, candidate.overall, -candidate.id, candidate,
                                         salary, years))
            if upgrades:
                *_, candidate, salary, years = max(upgrades)
                _bid(db, season, team, candidate, salary, years)
                targeted.add(candidate.id)
                budget -= salary

        for position in market.lost(team.id)[:open_spots - len(targeted)]:
            reserve = (open_spots - len(targeted) - 1) * ROSTER_SPOT_RESERVE
            options = []
            for candidate in by_position[position]:
                if candidate.id in targeted or market.departed_from.get(candidate.id) == team.id:
                    continue
                years = preferred_years(candidate.age)
                salary = int(round(price(candidate, years) * rng.uniform(*AI_SALARY_RANGE), -4))
                if salary + reserve <= budget:
                    options.append((candidate, salary, years))
                if len(options) == len(AI_CHOICES):
                    break
            if not options:
                continue
            candidate, salary, years = rng.choices(
                options, weights=AI_CHOICES[:len(options)])[0]
            _bid(db, season, team, candidate, salary, years)
            targeted.add(candidate.id)
            budget -= salary
    db.flush()


def _bid(db: Session, season: Season, team: Team, player: Player, salary: int,
         years: int) -> None:
    db.add(FreeAgentOffer(season_id=season.id, player_id=player.id, team_id=team.id,
                          salary=max(MIN_SALARY, salary), years=years,
                          day=season.free_agency_day))


def _resolve_day(db: Session, market: _Market) -> list[dict]:
    """Free agents, best first, take their best acceptable offer; returns the signings."""
    season = market.season
    day = season.free_agency_day
    offers = db.scalars(select(FreeAgentOffer).where(
        FreeAgentOffer.season_id == season.id, FreeAgentOffer.status == "pending")).all()
    by_player: dict[int, list[FreeAgentOffer]] = defaultdict(list)
    for offer in offers:
        by_player[offer.player_id].append(offer)
    strength = market.strength()
    teams = {t.id: t for t in market.teams}
    signings = []
    for player in list(market.pool):
        mine = by_player.get(player.id)
        if not mine:
            continue
        by_id = {o.id: o for o in mine}
        bids = [Bid(o.id, o.salary, price(player, o.years), strength[o.team_id])
                for o in mine if market.fits(o.team_id, o.salary)]
        best = next(iter(ranked(bids)), None)
        if best is None or not acceptable(best, day):
            continue
        winner = by_id[best.offer_id]
        market.sign(player, teams[winner.team_id], winner.salary, winner.years)
        for offer in mine:
            offer.status = "accepted" if offer is winner else "lost"
        signing = {"player": player.id, "team": winner.team_id, "salary": winner.salary,
                   "years": winner.years, "day": day}
        market.log.setdefault("signed", []).append(signing)
        signings.append(signing)
    market.save_log()
    db.flush()
    return signings


def _close(db: Session, market: _Market) -> None:
    """Expire what's left, fill every still-lost spot with an undrafted rookie, and move
    on to the preseason."""
    season = market.season
    for offer in db.scalars(select(FreeAgentOffer).where(
            FreeAgentOffer.season_id == season.id, FreeAgentOffer.status == "pending")):
        offer.status = "expired"
    rng = market_rng(market.league.id, season.year, 0)
    rookies = market.log.setdefault("rookies", [])
    for team in market.teams:
        roster = market.rosters[team.id]
        for position in list(market.lost(team.id)):
            if len(roster) >= ROSTER_MAX:
                break
            taken = {p.jersey_number for p in roster}
            with db.no_autoflush:
                rookie = _rookie(rng, market.league, Position(position), taken)
                rookie.team = team
                _sign(rookie, team, season.year, MIN_SALARY, rng.randint(3, 4))
                db.add(rookie)
            roster.append(rookie)
            market.payrolls[team.id] += MIN_SALARY
            market.lost(team.id).remove(position)
            db.flush()
            rookies.append(rookie.id)
    season.phase = "preseason"
    season.free_agency_day = 0
    market.save_log()
    db.flush()


def play_days(db: Session, season: Season, until: str) -> list[dict]:
    """Play the next market day, or every remaining day (`until="end"`); the market closes
    after the last one. Returns the signings."""
    _require_market(season)
    signings: list[dict] = []
    while season.phase == "free_agency":
        market = _Market(db, season)
        signings += _resolve_day(db, market)
        season.free_agency_day += 1
        if season.free_agency_day > MARKET_DAYS:
            _close(db, _Market(db, season))
        else:
            _ai_offers(db, _Market(db, season))
        if until == "next_day":
            break
    return signings


def make_offer(db: Session, player: Player, terms: ContractTerms) -> None:
    """The franchise offers a free agent a deal (replacing any earlier offer to him)."""
    season = current_season(db, player.league_id)
    _require_market(season)
    if player.team_id is not None or player.retired_year is not None:
        raise RosterError(f"{player.full_name} isn't a free agent.")
    team_id = franchise_team_id(db, player.league_id)
    if team_id is None:
        raise RosterError("This league has no franchise.", 400)
    market = _Market(db, season)
    if len(market.rosters[team_id]) >= ROSTER_MAX:
        raise RosterError(f"Your roster is full ({ROSTER_MAX}); release a player first.")
    if market.payrolls[team_id] + terms.salary > market.league.salary_cap:
        raise RosterError("That offer would put your payroll over the cap.")
    offer = _user_offer(db, season, player.id, team_id)
    if offer is None:
        offer = FreeAgentOffer(season_id=season.id, player_id=player.id, team_id=team_id)
        db.add(offer)
    offer.salary, offer.years, offer.day = terms.salary, terms.years, season.free_agency_day
    db.flush()


def withdraw_offer(db: Session, player: Player) -> None:
    season = current_season(db, player.league_id)
    _require_market(season)
    offer = _user_offer(db, season, player.id, franchise_team_id(db, player.league_id))
    if offer is None:
        raise RosterError("You haven't made him an offer.", 404)
    db.delete(offer)
    db.flush()


def _user_offer(db: Session, season: Season, player_id: int,
                team_id: int | None) -> FreeAgentOffer | None:
    return db.scalar(select(FreeAgentOffer).where(
        FreeAgentOffer.season_id == season.id, FreeAgentOffer.player_id == player_id,
        FreeAgentOffer.team_id == team_id, FreeAgentOffer.status == "pending"))


def market_view(db: Session, league: League) -> FreeAgencyOut:
    season = current_season(db, league.id)
    market = _Market(db, season)
    is_open = season.phase == "free_agency"
    offers: dict[int, list[FreeAgentOffer]] = defaultdict(list)
    if is_open:
        for offer in db.scalars(select(FreeAgentOffer).where(
                FreeAgentOffer.season_id == season.id, FreeAgentOffer.status == "pending")):
            offers[offer.player_id].append(offer)
    strength = market.strength() if offers else {}

    rows = []
    for player in market.pool:
        mine = next((o for o in offers[player.id] if o.team_id == market.user_team), None)
        leading = None
        if mine is not None:
            bids = [Bid(o.id, o.salary, price(player, o.years), strength[o.team_id])
                    for o in offers[player.id]]
            leading = ranked(bids)[0].offer_id == mine.id
        rows.append(FreeAgentRow(
            player=player_summary(player), asking=asking(player), offers=len(offers[player.id]),
            my_offer=ContractTerms(salary=mine.salary, years=mine.years) if mine else None,
            leading=leading))

    signings = signings_out(db, list(reversed(market.log.get("signed", []))))
    return FreeAgencyOut(
        season=season_view(db, season), open=is_open,
        day=season.free_agency_day if is_open else None, days=MARKET_DAYS,
        demand=demand(season.free_agency_day) if is_open else None,
        open_spots=ROSTER_MAX - len(market.rosters[market.user_team])
        if market.user_team else 0,
        cap_space=(league.salary_cap - market.payrolls[market.user_team])
        if market.user_team else 0,
        players=rows, signings=signings)


def signings_out(db: Session, entries: list[dict]) -> list[MarketSigning]:
    """Market signings (log entries with a `day`) for display."""
    entries = [e for e in entries if e.get("day")]
    players = {p.id: p for p in db.scalars(
        select(Player).where(Player.id.in_({e["player"] for e in entries}))
        .options(selectinload(Player.ratings), selectinload(Player.contracts)))}
    teams = {t.id: t for t in db.scalars(select(Team).where(
        Team.id.in_({e["team"] for e in entries})))}
    return [MarketSigning(player=player_summary(players[e["player"]]),
                          team=team_summary(teams[e["team"]]), salary=e["salary"],
                          years=e["years"], day=e["day"])
            for e in entries if e["player"] in players]
