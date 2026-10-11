"""Year rollover: the offseason between a crowned champion and the next season.

`advance` runs every offseason step in one deterministic pass and records what happened
in the new season's `offseason_log`:

1. Aging and development (growth toward potential, decline past 30); injuries heal.
2. Retirements.
3. Expiring contracts: AI teams re-sign at market value while the cap allows (keeping room
   to fill the roster); fading depth veterans aren't re-signed. The franchise's players
   re-signed during the offseason window (services/contracts.py) stay; the rest leave.
4. Every roster spot lost is refilled at the same position with the best affordable free
   agent, or else an undrafted rookie; the free-agent pool is topped up.

Step 4 is automatic for every team, the user's included, until free agency and the
draft get their own screens.
5. A new season with a fresh schedule.
"""

import hashlib
import random
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.contracts import MIN_SALARY, market_salary
from app.domain.development import contract_years, develop, retirement_chance
from app.domain.positions import ROSTER_MAX, ROSTER_TEMPLATE, Position, available_jersey
from app.domain.ratings import clamp_rating
from app.models import Contract, Franchise, Player, Season, Team
from app.seed.generator import (
    FREE_AGENT_COUNT,
    _development_trait,
    _schedule,
    make_player,
)
from app.services import playoffs
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.injuries import heal

if TYPE_CHECKING:
    from app.schemas import OffseasonRecap

ROSTER_SPOT_RESERVE = 1_000_000  # cap room kept per open roster spot while re-signing
ROOKIE_TARGET = (60, 5)  # mean, sd of a rookie's OVR
ROOKIE_UPSIDE = (14, 8)  # mean, sd of potential above OVR
VETERAN_KEEP = (30, 70)  # teams let expiring players this old and below this OVR walk
FREE_AGENT_FLOOR = 64  # teams prefer an undrafted rookie to a free agent below this OVR
FREE_AGENT_TARGET = (62, 5)
RECAP_MOVERS = 5


def offseason_rng(league_id: int, year: int) -> random.Random:
    digest = hashlib.sha256(f"offseason:{league_id}:{year}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _leave_team(db: Session, player: Player) -> None:
    for contract in player.contracts:
        contract.is_active = False
    remove_player(db, player)
    player.team_id = None


def advance(db: Session, season: Season) -> Season:
    """Run the offseason after `season` and create the next one."""
    if season.phase != "offseason":
        raise RosterError("Finish the playoffs before starting the next season.")
    if db.scalar(select(Season.id).where(Season.league_id == season.league_id,
                                         Season.year > season.year)):
        raise RosterError("The next season has already started.")
    league = season.league
    year = season.year + 1
    rng = offseason_rng(league.id, year)
    log: dict = {"from_year": season.year, "retired": [], "departed": [], "re_signed": [],
                 "signed": [], "rookies": [], "development": {}}

    players = list(db.scalars(
        select(Player)
        .where(Player.league_id == league.id, Player.retired_year.is_(None))
        .options(selectinload(Player.ratings), selectinload(Player.contracts))
        .order_by(Player.id)))

    # 1. Aging and development.
    for player in players:
        before = player.overall
        player.age += 1
        player.years_pro += 1
        result = develop(rng, player.position, player.age, player.ratings.as_dict(),
                         player.potential, player.development_trait)
        for name, value in result.ratings.items():
            setattr(player.ratings, name, value)
        player.overall = result.overall
        player.potential = result.potential
        heal(player)
        if player.team_id is not None:
            log["development"][str(player.id)] = [before, player.overall]

    # 2. Retirements.
    lost: dict[int, list[str]] = defaultdict(list)  # team -> positions to refill
    for player in players:
        signed = player.team_id is not None
        if rng.random() < retirement_chance(player.position, player.age, player.overall, signed):
            log["retired"].append({"player": player.id, "team": player.team_id})
            if signed:
                lost[player.team_id].append(player.position)
                _leave_team(db, player)
            player.retired_year = season.year

    # 3. Expiring contracts.
    teams = list(db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)))
    active = [p for p in players if p.retired_year is None]
    rosters: dict[int, list[Player]] = defaultdict(list)
    for player in active:
        if player.team_id is not None:
            rosters[player.team_id].append(player)
    payrolls: dict[int, int] = {}
    departed_from: dict[int, int] = {}  # a team doesn't sign back who it just let go
    cap = league.salary_cap
    # The franchise decides its own re-signings (services/contracts.py); whoever it
    # didn't re-sign leaves.
    user_team = db.scalar(select(Franchise.team_id).where(Franchise.league_id == league.id))
    for team in teams:
        roster = rosters[team.id]
        expiring = [p for p in roster if p.active_contract.end_year <= season.year]
        staying = [p for p in roster if p not in expiring]
        payroll = sum(p.active_contract.salary for p in staying)
        committed = len(staying)
        for player in sorted(expiring, key=lambda p: (-p.overall, p.id)):
            salary = market_salary(Position(player.position), player.overall)
            # Keep enough room to fill the rest of the roster.
            reserve = max(0, ROSTER_MAX - committed - 1) * ROSTER_SPOT_RESERVE
            worth_keeping = team.id != user_team and (
                player.age < VETERAN_KEEP[0] or player.overall >= VETERAN_KEEP[1])
            if worth_keeping and payroll + salary + reserve <= cap:
                years = contract_years(rng, player.age)
                _sign(player, team, year, salary, years)
                payroll += salary
                committed += 1
                log["re_signed"].append({"player": player.id, "team": team.id,
                                         "salary": salary, "years": years})
            else:
                log["departed"].append({"player": player.id, "team": team.id})
                departed_from[player.id] = team.id
                lost[team.id].append(player.position)
                _leave_team(db, player)
                roster.remove(player)
        payrolls[team.id] = payroll

    # 4. Refill the spots that opened up, a round at a time so no team hogs the market:
    # the best affordable free agent at the position, otherwise an undrafted rookie.
    pool: dict[str, list[Player]] = defaultdict(list)
    for player in sorted((p for p in active if p.team_id is None),
                         key=lambda p: (-p.overall, p.id)):
        pool[player.position].append(player)
    order = list(teams)
    rng.shuffle(order)
    rookies: list[Player] = []
    for round_index in range(max((len(v) for v in lost.values()), default=0)):
        for team in order:
            roster = rosters[team.id]
            if round_index >= len(lost[team.id]) or len(roster) >= ROSTER_MAX:
                continue
            position = lost[team.id][round_index]
            reserve = (ROSTER_MAX - len(roster) - 1) * ROSTER_SPOT_RESERVE
            budget = cap - payrolls[team.id] - reserve
            signing = next((p for p in pool[position] if p.overall >= FREE_AGENT_FLOOR
                            and departed_from.get(p.id) != team.id
                            and market_salary(Position(position), p.overall) <= budget), None)
            taken = {p.jersey_number for p in roster}
            if signing is not None:
                pool[position].remove(signing)
                salary = market_salary(Position(position), signing.overall)
                years = contract_years(rng, signing.age)
                if signing.jersey_number in taken:
                    signing.jersey_number = available_jersey(position, taken)
                signing.team_id = team.id
                _sign(signing, team, year, salary, years)
                log["signed"].append({"player": signing.id, "team": team.id,
                                      "salary": salary, "years": years})
            else:
                with db.no_autoflush:
                    signing = _rookie(rng, league, Position(position), taken)
                    salary = MIN_SALARY  # undrafted rookies sign for the minimum
                    signing.team = team
                    _sign(signing, team, year, salary, rng.randint(3, 4))
                    db.add(signing)
                rookies.append(signing)
            roster.append(signing)
            payrolls[team.id] += salary
    db.flush()
    log["rookies"] = [p.id for p in rookies]

    free_agents = sum(1 for p in active if p.team_id is None)
    positions, weights = list(ROSTER_TEMPLATE), list(ROSTER_TEMPLATE.values())
    for _ in range(max(0, FREE_AGENT_COUNT - free_agents)):
        position = rng.choices(positions, weights=weights)[0]
        db.add(make_player(rng, league, position, round(rng.gauss(*FREE_AGENT_TARGET)),
                           age=rng.randint(22, 25)))

    # 5. The new season.
    weeks = playoffs.regular_week_count(db, season.id)
    new_season = Season(league=league, year=year, phase="preseason", current_week=1,
                        offseason_log=log)
    db.add(new_season)
    _schedule(db, new_season, [t.id for t in teams], rng, weeks)
    db.flush()
    return new_season


def _sign(player: Player, team: Team, year: int, salary: int, years: int) -> None:
    if player.active_contract is not None:
        player.active_contract.is_active = False
    player.contracts.append(Contract(team_id=team.id, start_year=year, years=years,
                                     salary=salary))


def _rookie(rng: random.Random, league, position: Position, taken: set[int]) -> Player:
    rookie = make_player(rng, league, position, round(rng.gauss(*ROOKIE_TARGET)),
                         taken_numbers=taken, age=rng.randint(21, 23))
    rookie.years_pro = 0
    rookie.potential = clamp_rating(rookie.overall + max(2, rng.gauss(*ROOKIE_UPSIDE)))
    rookie.development_trait = _development_trait(rng, rookie.potential)
    return rookie


def recap(db: Session, season: Season, team_id: int) -> "OffseasonRecap | None":
    """What the offseason before `season` meant for one team (plus notable retirements)."""
    from app.schemas import OffseasonRecap, RecapMove, RecapRetirement, RecapSigning
    from app.services.serializers import player_summary, team_summary

    log = season.offseason_log
    if not log:
        return None
    ids = {e["player"] for key in ("retired", "departed", "re_signed", "signed")
           for e in log[key]}
    ids |= set(log["rookies"]) | {int(k) for k in log["development"]}
    players = {p.id: p for p in db.scalars(
        select(Player).where(Player.id.in_(ids))
        .options(selectinload(Player.ratings), selectinload(Player.contracts)))}
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.league_id == season.league_id))}

    def mine(key: str) -> list:
        return [players[e["player"]] for e in log[key] if e["team"] == team_id]

    def signings(key: str) -> list[RecapSigning]:
        return [RecapSigning(player=player_summary(players[e["player"]]), salary=e["salary"],
                             years=e["years"]) for e in log[key] if e["team"] == team_id]

    changes = [(players[int(pid)], before, after)
               for pid, (before, after) in log["development"].items()
               if players[int(pid)].team_id == team_id]
    risers = sorted((c for c in changes if c[2] > c[1]), key=lambda c: (c[1] - c[2], c[0].id))
    decliners = sorted((c for c in changes if c[2] < c[1]), key=lambda c: (c[2] - c[1], c[0].id))
    notable = sorted(log["retired"], key=lambda e: (-players[e["player"]].overall, e["player"]))

    return OffseasonRecap(
        from_year=log["from_year"], year=season.year,
        retired=[player_summary(p) for p in mine("retired")],
        departed=[player_summary(p) for p in mine("departed")],
        re_signed=signings("re_signed"),
        signed=signings("signed"),
        rookies=[player_summary(players[pid]) for pid in log["rookies"]
                 if players[pid].team_id == team_id],
        risers=[RecapMove(player=player_summary(p), before=b, after=a)
                for p, b, a in risers[:RECAP_MOVERS]],
        decliners=[RecapMove(player=player_summary(p), before=b, after=a)
                   for p, b, a in decliners[:RECAP_MOVERS]],
        league_retirements=[
            RecapRetirement(player=player_summary(players[e["player"]]),
                            team=team_summary(teams[e["team"]]) if e["team"] else None)
            for e in notable[:RECAP_MOVERS]],
    )
