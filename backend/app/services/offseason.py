"""Year rollover: the offseason between a crowned champion and the next season.

`advance` runs every offseason step in one deterministic pass and records what happened
in the new season's `offseason_log`:

1. Aging and development (growth toward potential, decline past 30); injuries heal.
2. Retirements (and the tail of an overcrowded free-agent pool).
3. Expiring contracts: AI teams re-sign at market value while the cap allows (keeping room
   to fill the roster); fading depth veterans aren't re-signed. The franchise's players
   re-signed during the offseason window (services/contracts.py) stay; the rest leave.
4. The positions each team lost are recorded; the free-agent pool is topped up.
5. A new season with a fresh schedule, opening with free agency (services/free_agency.py):
   teams refill those spots in the market, then in the draft (services/draft.py).
"""

import hashlib
import random
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.contracts import market_salary
from app.domain.development import contract_years, develop, retirement_chance
from app.domain.positions import ROSTER_MAX, ROSTER_TEMPLATE, Position
from app.models import Contract, Player, Season, Team
from app.seed.generator import (
    FREE_AGENT_COUNT,
    _schedule,
    make_player,
)
from app.services import cap, playoffs
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.injuries import heal
from app.services.members import human_team_ids

if TYPE_CHECKING:
    from app.schemas import OffseasonRecap

ROSTER_SPOT_RESERVE = 1_000_000  # cap room kept per open roster spot while re-signing
VETERAN_KEEP = (30, 70)  # teams let expiring players this old and below this OVR walk
FREE_AGENT_FLOOR = 64  # AI teams don't bid on free agents below this OVR
FREE_AGENT_TARGET = (62, 5)
FREE_AGENT_POOL_MAX = 250  # unsigned players kept from one offseason to the next
RECAP_MOVERS = 5


def offseason_rng(league_id: int, year: int) -> random.Random:
    digest = hashlib.sha256(f"offseason:{league_id}:{year}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _leave_team(db: Session, player: Player) -> None:
    for contract in player.contracts:
        contract.is_active = False
    remove_player(db, player)
    player.team_id = None


def advance(db: Session, season: Season, autopilot: bool = False) -> Season:
    """Run the offseason after `season` and create the next one, in free agency."""
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
        .where(Player.league_id == league.id, Player.retired_year.is_(None),
               Player.is_prospect.is_(False))
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
                # Retiring mid-deal leaves the rest of his bonus on next season's cap.
                cap.charge(db, player, player.active_contract, year, "retired")
                _leave_team(db, player)
            player.retired_year = season.year
    # Nobody signs a crowded pool's tail: past FREE_AGENT_POOL_MAX, the least valuable
    # unsigned players (lowest OVR, older first) leave football.
    pool = sorted((p for p in players if p.team_id is None and p.retired_year is None),
                  key=lambda p: (-(p.overall - max(0, p.age - 28) * 2), p.id))
    for player in pool[FREE_AGENT_POOL_MAX:]:
        log["retired"].append({"player": player.id, "team": None})
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
    salary_cap = league.salary_cap
    # Each team a member runs decides its own re-signings (services/contracts.py); whoever
    # it didn't re-sign leaves. On autopilot (sim ahead) the franchise re-signs like an AI.
    humans = set() if autopilot else human_team_ids(db, league.id)
    db.flush()
    dead = cap.dead_money_totals(db, [t.id for t in teams], year)
    for team in teams:
        roster = rosters[team.id]
        expiring = [p for p in roster if p.active_contract.end_year <= season.year]
        staying = [p for p in roster if p not in expiring]
        payroll = sum(p.active_contract.salary for p in staying) + dead[team.id]
        committed = len(staying)
        for player in sorted(expiring, key=lambda p: (-p.overall, p.id)):
            salary = market_salary(Position(player.position), player.overall)
            # Keep enough room to fill the rest of the roster.
            reserve = max(0, ROSTER_MAX - committed - 1) * ROSTER_SPOT_RESERVE
            worth_keeping = team.id not in humans and (
                player.age < VETERAN_KEEP[0] or player.overall >= VETERAN_KEEP[1])
            if worth_keeping and payroll + salary + reserve <= salary_cap:
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

    # 4. Spots to refill in free agency and the draft.
    log["lost"] = {str(team_id): positions for team_id, positions in lost.items()}
    db.flush()

    free_agents = sum(1 for p in active if p.team_id is None)
    positions, weights = list(ROSTER_TEMPLATE), list(ROSTER_TEMPLATE.values())
    for _ in range(max(0, FREE_AGENT_COUNT - free_agents)):
        position = rng.choices(positions, weights=weights)[0]
        db.add(make_player(rng, league, position, round(rng.gauss(*FREE_AGENT_TARGET)),
                           age=rng.randint(22, 25)))

    # 5. The new season, opening with free agency.
    weeks = playoffs.regular_week_count(db, season.id)
    new_season = Season(league=league, year=year, phase="free_agency", current_week=1,
                        free_agency_day=1, offseason_log=log)
    db.add(new_season)
    _schedule(db, new_season, [t.id for t in teams], rng, weeks)
    db.flush()
    # 6. Older seasons keep full play-by-play only where it matters (compaction.py).
    from app.services import compaction, free_agency  # (they build on this module)

    compaction.compact_old_seasons(db, league.id, year)

    free_agency.open_market(db, new_season)
    return new_season


def _sign(player: Player, team: Team, year: int, salary: int, years: int) -> None:
    if player.active_contract is not None:
        player.active_contract.is_active = False
    player.contracts.append(Contract.signed(team.id, year, years, salary))


def recap(db: Session, season: Season, team_id: int, roster: "list[Player] | None" = None,
          teams: "dict[int, Team] | None" = None) -> "OffseasonRecap | None":
    """What the offseason before `season` meant for one team (plus notable retirements).
    Pass the team's roster (with ratings and contracts) and the league's teams when
    recapping several seasons."""
    from app.schemas import OffseasonRecap, RecapMove, RecapRetirement, RecapSigning
    from app.services.serializers import player_summary, team_summary

    log = season.offseason_log
    if not log:
        return None
    # Load (with ratings and contracts) only the players the recap shows: this team's
    # moves, its rookies, and the league's most notable retirements.
    ids = {e["player"] for key in ("retired", "departed", "re_signed", "signed")
           for e in log[key] if e["team"] == team_id}
    drafted = [e["player"] for e in log.get("drafted", []) if e["team"] == team_id]
    ids |= set(drafted) | set(db.scalars(select(Player.id).where(
        Player.id.in_(log["rookies"]), Player.team_id == team_id)))
    retired_overall = dict(db.execute(select(Player.id, Player.overall).where(
        Player.id.in_([e["player"] for e in log["retired"]]))).all())
    notable = sorted((e for e in log["retired"] if e["player"] in retired_overall),
                     key=lambda e: (-retired_overall[e["player"]], e["player"]))[:RECAP_MOVERS]
    ids |= {e["player"] for e in notable}
    loading = (selectinload(Player.ratings), selectinload(Player.contracts))
    players = {p.id: p for p in db.scalars(
        select(Player).where(Player.id.in_(ids)).options(*loading))}
    # Risers and decliners: of the whole league's rating changes, only this team's
    # players matter, so load its roster rather than every player who changed.
    if roster is None:
        roster = list(db.scalars(select(Player).where(Player.team_id == team_id)
                                 .options(*loading)))
    players.update({p.id: p for p in roster if str(p.id) in log["development"]})
    if teams is None:
        teams = {t.id: t for t in db.scalars(select(Team).where(
            Team.league_id == season.league_id))}

    def mine(key: str) -> list:
        return [players[e["player"]] for e in log[key] if e["team"] == team_id]

    def signings(key: str) -> list[RecapSigning]:
        return [RecapSigning(player=player_summary(players[e["player"]]), salary=e["salary"],
                             years=e["years"]) for e in log[key] if e["team"] == team_id]

    changes = [(players[int(pid)], before, after)
               for pid, (before, after) in log["development"].items()
               if int(pid) in players and players[int(pid)].team_id == team_id]
    risers = sorted((c for c in changes if c[2] > c[1]), key=lambda c: (c[1] - c[2], c[0].id))
    decliners = sorted((c for c in changes if c[2] < c[1]), key=lambda c: (c[2] - c[1], c[0].id))

    return OffseasonRecap(
        from_year=log["from_year"], year=season.year,
        retired=[player_summary(p) for p in mine("retired")],
        departed=[player_summary(p) for p in mine("departed")],
        re_signed=signings("re_signed"),
        signed=signings("signed"),
        rookies=[player_summary(players[pid]) for pid in [*drafted, *log["rookies"]]
                 if pid in players and players[pid].team_id == team_id],  # picks, then UDFAs
        risers=[RecapMove(player=player_summary(p), before=b, after=a)
                for p, b, a in risers[:RECAP_MOVERS]],
        decliners=[RecapMove(player=player_summary(p), before=b, after=a)
                   for p, b, a in decliners[:RECAP_MOVERS]],
        league_retirements=[
            RecapRetirement(player=player_summary(players[e["player"]]),
                            team=team_summary(teams[e["team"]]) if e["team"] else None)
            for e in notable],
    )
