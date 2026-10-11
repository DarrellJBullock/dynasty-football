"""The draft: classes of fictional prospects, scouting, draft order, picks, and what
happens after (undrafted free agents, roster cut-downs).

A class for year Y is generated (deterministically) when it's first needed: the franchise
scouts it during season Y-1, and it's drafted in season Y after free agency (phase
"draft"). Then the season moves to the preseason.
"""

import hashlib
import random
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.domain.contracts import MIN_SALARY, market_salary
from app.domain.draft import (
    PROJECTION_RANGE,
    ROOKIE_YEARS,
    ROUNDS,
    SCOUTING_REPORTS,
    Finish,
    ai_value,
    class_size,
    draft_order,
    potential_grade,
    prospect_target,
    rookie_salary,
    scout_noise,
)
from app.domain.positions import (
    ROSTER_MAX,
    ROSTER_TEMPLATE,
    SPECIAL_TEAMS,
    Position,
    available_jersey,
)
from app.domain.ratings import clamp_rating
from app.models import Contract, DraftPick, Game, League, Player, Season, Team
from app.schemas import DraftOut, DraftPickOut, ProspectRow
from app.seed.generator import SPECIALIST_OFFSET, _development_trait, make_player
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.free_agency import franchise_team_id
from app.services.serializers import player_summary, team_summary
from app.services.standings import compute_records
from app.services.teams import current_season

UDFA_YEARS = 3
CANDIDATES = 40  # an AI team weighs the best few dozen prospects left on its board


def _rng(*parts: object) -> random.Random:
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def class_year(db: Session, season: Season) -> int:
    """The class the franchise is looking at: this year's during free agency, the draft,
    and the preseason after it; next year's once the season is under way (or in a new
    league's first preseason, which had no draft)."""
    if season.phase in ("free_agency", "draft"):
        return season.year
    if season.phase == "preseason" and db.scalar(
            select(DraftPick.id).where(DraftPick.season_id == season.id).limit(1)):
        return season.year
    return season.year + 1


def ensure_class(db: Session, league: League, year: int) -> None:
    """Generate the `year` draft class once (the same class every time)."""
    if db.scalar(select(func.count(Player.id)).where(Player.league_id == league.id,
                                                     Player.draft_year == year)):
        return
    teams = db.scalar(select(func.count(Team.id)).where(Team.league_id == league.id)) or 0
    rng = _rng("draft-class", league.id, year)
    positions, weights = list(ROSTER_TEMPLATE), list(ROSTER_TEMPLATE.values())
    size = class_size(teams)
    for rank in range(size):
        position = rng.choices(positions, weights=weights)[0]
        target, upside = prospect_target(rng, rank, size)
        if position in SPECIAL_TEAMS:
            target += SPECIALIST_OFFSET  # (their OVR averages only two attributes)
        prospect = make_player(rng, league, position, target, age=rng.randint(21, 23))
        prospect.years_pro = 0
        prospect.potential = clamp_rating(prospect.overall + upside)
        prospect.development_trait = _development_trait(rng, prospect.potential)
        prospect.is_prospect = True
        prospect.draft_year = year
        db.add(prospect)
    db.flush()


def _prospects(db: Session, league_id: int, year: int) -> list[Player]:
    """Prospects still available in a class, best (true) first."""
    return list(db.scalars(
        select(Player).where(Player.league_id == league_id, Player.draft_year == year,
                             Player.is_prospect)
        .options(selectinload(Player.ratings), selectinload(Player.contracts))
        .order_by(Player.overall.desc(), Player.id)))


# ---------- scouting ----------


def prospect_key(player: Player) -> str:
    return (f"{player.draft_year}:{player.first_name} {player.last_name}:{player.position}:"
            f"{player.college}:{player.height_in}:{player.weight_lb}")


def projection(league_id: int, player: Player) -> tuple[int, int]:
    """The franchise's view of a prospect: (OVR, potential), exact once scouted."""
    if player.scouted:
        return player.overall, player.potential
    noise = scout_noise(league_id, prospect_key(player))
    return clamp_rating(player.overall + noise), clamp_rating(player.potential + noise)


def prospect_row(league_id: int, player: Player) -> ProspectRow:
    ovr, potential = projection(league_id, player)
    spread = 0 if player.scouted else PROJECTION_RANGE
    return ProspectRow(
        id=player.id, full_name=player.full_name, position=player.position, age=player.age,
        college=player.college, height_in=player.height_in, weight_lb=player.weight_lb,
        projected=ovr, low=ovr - spread, high=ovr + spread, grade=potential_grade(potential),
        scouted=player.scouted, overall=player.overall if player.scouted else None,
        potential=player.potential if player.scouted else None)


def scouting_left(db: Session, league_id: int, year: int) -> int:
    used = db.scalar(select(func.count(Player.id)).where(
        Player.league_id == league_id, Player.draft_year == year, Player.scouted)) or 0
    return max(0, SCOUTING_REPORTS - used)


def scout(db: Session, player: Player) -> ProspectRow:
    season = current_season(db, player.league_id)
    if not player.is_prospect or player.draft_year != class_year(db, season):
        raise RosterError(f"{player.full_name} isn't in the draft class you're scouting.")
    if not player.scouted:
        if scouting_left(db, player.league_id, player.draft_year) <= 0:
            raise RosterError(f"No scouting reports left ({SCOUTING_REPORTS} per class).")
        player.scouted = True
        db.flush()
    return prospect_row(player.league_id, player)


# ---------- draft order ----------


def open_draft(db: Session, season: Season) -> None:
    """Called when free agency closes: set the order (from last season) and go live."""
    league = season.league
    ensure_class(db, league, season.year)
    teams = list(db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)))
    previous = db.scalar(select(Season).where(Season.league_id == league.id,
                                              Season.year == season.year - 1))
    finishes = _finishes(db, previous, teams) if previous else [
        Finish(t.id, 0, 0.0, 0) for t in teams]
    order = draft_order(finishes, salt=f"draft:{league.id}:{season.year}")
    for round_number in range(1, ROUNDS + 1):
        for index, team_id in enumerate(order):
            db.add(DraftPick(season_id=season.id, round=round_number,
                             number=(round_number - 1) * len(order) + index + 1,
                             team_id=team_id))
    season.phase = "draft"
    db.flush()


def _finishes(db: Session, season: Season, teams: list[Team]) -> list[Finish]:
    records = compute_records(db, season, [t.id for t in teams])
    deepest: dict[int, int] = defaultdict(int)
    for game in db.scalars(select(Game).where(Game.season_id == season.id,
                                              Game.stage == "playoff")):
        for team_id in (game.home_team_id, game.away_team_id):
            deepest[team_id] = max(deepest[team_id], game.playoff_round or 0)
    if season.champion_team_id:
        deepest[season.champion_team_id] += 1
    return [Finish(t.id, deepest[t.id], records[t.id].win_pct,
                   records[t.id].points_for - records[t.id].points_against) for t in teams]


# ---------- picks ----------


def _picks(db: Session, season: Season) -> list[DraftPick]:
    return list(db.scalars(select(DraftPick).where(DraftPick.season_id == season.id)
                           .order_by(DraftPick.number)))


def on_the_clock(db: Session, season: Season) -> DraftPick | None:
    if season.phase != "draft":
        return None
    return db.scalar(select(DraftPick).where(DraftPick.season_id == season.id,
                                            DraftPick.player_id.is_(None))
                     .order_by(DraftPick.number))


def _roster(db: Session, team_id: int) -> list[Player]:
    return list(db.scalars(select(Player).where(Player.team_id == team_id)
                           .options(selectinload(Player.contracts))))


def _lost(season: Season, team_id: int) -> list[str]:
    log = season.offseason_log if season.offseason_log is not None else {}
    season.offseason_log = log
    return log.setdefault("lost", {}).setdefault(str(team_id), [])


def _join(season: Season, player: Player, team_id: int, salary: int, years: int,
          taken: set[int]) -> None:
    """Sign `player` to the team; `taken` (its jersey numbers) is updated."""
    if player.jersey_number in taken:
        player.jersey_number = available_jersey(player.position, taken)
    taken.add(player.jersey_number)
    player.team_id = team_id
    player.is_prospect = False
    player.contracts.append(Contract(team_id=team_id, start_year=season.year, years=years,
                                     salary=salary))
    lost = _lost(season, team_id)
    if player.position in lost:
        lost.remove(player.position)


class _Board:
    """What a run of picks needs, loaded once: the prospects left, and each team's
    position counts and jersey numbers."""

    def __init__(self, db: Session, season: Season):
        self.available = _prospects(db, season.league_id, season.year)
        self.counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.jerseys: dict[int, set[int]] = defaultdict(set)
        for team_id, position, jersey in db.execute(
                select(Player.team_id, Player.position, Player.jersey_number)
                .join(Team, Team.id == Player.team_id)
                .where(Team.league_id == season.league_id)):
            self.counts[team_id][position] += 1
            self.jerseys[team_id].add(jersey)

    def needs(self, season: Season, team_id: int) -> set[str]:
        """Positions the team lost and hasn't refilled, or is below its usual count at."""
        counts = self.counts[team_id]
        short = {p.value for p, n in ROSTER_TEMPLATE.items() if counts[p.value] < n}
        return short | set(_lost(season, team_id))

    def take(self, player: Player, team_id: int) -> None:
        self.available.remove(player)
        self.counts[team_id][player.position] += 1


def _make_pick(db: Session, season: Season, pick: DraftPick, player: Player,
               board: _Board) -> None:
    _join(season, player, pick.team_id, rookie_salary(pick.number, MIN_SALARY), ROOKIE_YEARS,
          board.jerseys[pick.team_id])
    board.take(player, pick.team_id)
    player.draft_round = pick.round
    player.draft_pick = pick.number
    pick.player_id = player.id
    season.offseason_log.setdefault("drafted", []).append(
        {"player": player.id, "team": pick.team_id, "round": pick.round, "pick": pick.number})
    flag_modified(season, "offseason_log")


def _auto_pick(season: Season, pick: DraftPick, board: _Board, user: bool) -> Player:
    """AI teams value prospects by their own (noisy) read of OVR and potential; the
    franchise's auto-pick uses its scouting projection. Both favour positions of need."""
    league_id = season.league_id
    if not board.available:
        raise RosterError("No prospects left.")
    needs = board.needs(season, pick.team_id)
    rng = _rng("draft-pick", league_id, season.year, pick.number)
    if user:
        def value(p: Player) -> float:
            ovr, potential = projection(league_id, p)
            return ai_value(rng, ovr, potential, p.position in needs)
    else:
        def value(p: Player) -> float:
            return ai_value(rng, p.overall, p.potential, p.position in needs)
    candidates = sorted(board.available, key=lambda p: -(p.overall + p.potential))[:CANDIDATES]
    return max(candidates, key=lambda p: (value(p), -p.id))


def user_pick(db: Session, league: League, player_id: int) -> DraftPick:
    season = current_season(db, league.id)
    pick = on_the_clock(db, season)
    if pick is None:
        raise RosterError("The draft isn't live.")
    if pick.team_id != franchise_team_id(db, league.id):
        raise RosterError("You're not on the clock.")
    player = db.get(Player, player_id)
    if (player is None or player.league_id != league.id or not player.is_prospect
            or player.draft_year != season.year):
        raise RosterError("That player isn't available.")
    _make_pick(db, season, pick, player, _Board(db, season))
    db.flush()
    return pick


def play(db: Session, season: Season, until: str) -> list[DraftPick]:
    """Make picks until the franchise is on the clock (`my_pick`) or to the end (`end`,
    auto-picking for the franchise); after the last pick the draft wraps up."""
    if season.phase != "draft":
        raise RosterError("The draft isn't live.")
    user_team = franchise_team_id(db, season.league_id)
    board = _Board(db, season)
    remaining = [p for p in _picks(db, season) if p.player_id is None]
    made: list[DraftPick] = []
    for pick in remaining:
        mine = pick.team_id == user_team
        if mine and until == "my_pick":
            break
        _make_pick(db, season, pick, _auto_pick(season, pick, board, user=mine), board)
        made.append(pick)
    db.flush()
    if on_the_clock(db, season) is None:
        _finish(db, season)
    return made


def _finish(db: Session, season: Season) -> None:
    """Fill the spots teams still lost — the best undrafted prospect at the position, then
    the best one left, then a veteran free agent on a one-year minimum deal — make the
    rest of the class free agents, cut AI teams down to 53, and start the preseason."""
    league_id = season.league_id
    log = season.offseason_log
    user_team = franchise_team_id(db, league_id)
    undrafted = _prospects(db, league_id, season.year)
    veterans = list(db.scalars(
        select(Player).where(Player.league_id == league_id, Player.team_id.is_(None),
                             Player.retired_year.is_(None), Player.is_prospect.is_(False))
        .options(selectinload(Player.contracts))
        .order_by(Player.overall.desc(), Player.id)))
    teams = list(db.scalars(select(Team).where(Team.league_id == league_id).order_by(Team.id)))
    for team in teams:
        roster = _roster(db, team.id)
        lost = _lost(season, team.id)
        while lost and len(roster) < ROSTER_MAX and (undrafted or veterans):
            player = (next((p for p in undrafted if p.position == lost[0]), None)
                      or (undrafted[0] if undrafted else veterans[0]))
            fills_own_spot = player.position in lost  # (then _join crosses it off)
            taken = {p.jersey_number for p in roster}
            if player.is_prospect:
                undrafted.remove(player)
                _join(season, player, team.id, MIN_SALARY, UDFA_YEARS, taken)
                log.setdefault("rookies", []).append(player.id)
            else:
                veterans.remove(player)
                _join(season, player, team.id, MIN_SALARY, 1, taken)
                log.setdefault("signed", []).append(
                    {"player": player.id, "team": team.id, "salary": MIN_SALARY, "years": 1,
                     "day": 0})
            if not fills_own_spot:
                lost.pop(0)  # he takes the spot of the position at the head of the list
            roster.append(player)
    for player in undrafted:
        player.is_prospect = False  # unsigned: free agents now
    cuts = log.setdefault("cut", [])
    cap = season.league.salary_cap
    for team in teams:
        if team.id == user_team:
            continue
        roster = _roster(db, team.id)
        for player in sorted(roster, key=lambda p: (p.overall, -p.age, p.id))[
                :max(0, len(roster) - ROSTER_MAX)]:
            _release(db, player)
            cuts.append({"player": player.id, "team": team.id})
        _fit_under_cap(db, season, team, cap, veterans, cuts)
    season.phase = "preseason"
    flag_modified(season, "offseason_log")
    db.flush()


def _fit_under_cap(db: Session, season: Season, team: Team, cap: int,
                   veterans: list[Player], cuts: list[dict]) -> None:
    """Rookie deals can push a team over the cap: release the most overpaid veterans
    (salary furthest above market value; never this year's picks), each replaced by a
    free agent on a one-year minimum deal, until it fits."""
    roster = _roster(db, team.id)
    payroll = sum(c.salary for p in roster if (c := p.active_contract))
    candidates = sorted(
        (p for p in roster if p.draft_year != season.year and p.active_contract
         and p.active_contract.salary > MIN_SALARY),
        key=lambda p: (-(p.active_contract.salary
                         - market_salary(Position(p.position), p.overall)), p.id))
    for player in candidates:
        if payroll <= cap:
            break
        payroll -= player.active_contract.salary
        _release(db, player)
        cuts.append({"player": player.id, "team": team.id})
        roster.remove(player)
        if veterans:
            replacement = veterans.pop(0)
            _join(season, replacement, team.id, MIN_SALARY, 1,
                  {p.jersey_number for p in roster})
            roster.append(replacement)
            payroll += MIN_SALARY


def _release(db: Session, player: Player) -> None:
    for contract in player.contracts:
        contract.is_active = False
    remove_player(db, player)
    player.team_id = None


def cut_down(db: Session, team: Team) -> list[Player]:
    """Release the lowest-rated players until the roster is at 53."""
    roster = _roster(db, team.id)
    excess = sorted(roster, key=lambda p: (p.overall, -p.age, p.id))[
        :max(0, len(roster) - ROSTER_MAX)]
    for player in excess:
        _release(db, player)
    db.flush()
    return excess


# ---------- view ----------


def pick_out(pick: DraftPick, teams: int) -> DraftPickOut:
    return DraftPickOut(round=pick.round, number=pick.number,
                        pick_in_round=pick.number - (pick.round - 1) * teams,
                        team=team_summary(pick.team),
                        player=player_summary(pick.player) if pick.player else None)


def team_count(db: Session, league_id: int) -> int:
    return db.scalar(select(func.count(Team.id)).where(Team.league_id == league_id)) or 0


def draft_view(db: Session, league: League) -> DraftOut:
    from app.services.season import season_view

    season = current_season(db, league.id)
    year = class_year(db, season)
    ensure_class(db, league, year)
    user_team = franchise_team_id(db, league.id)
    picks = _picks(db, season) if year == season.year else []
    clock = on_the_clock(db, season)
    status = "live" if clock else "complete" if picks else "upcoming"
    prospects = sorted((prospect_row(league.id, p) for p in _prospects(db, league.id, year)),
                       key=lambda r: (-r.projected, r.id))
    roster_count = len(_roster(db, user_team)) if user_team else 0
    teams = team_count(db, league.id)
    return DraftOut(
        season=season_view(db, season), year=year, status=status,
        picks=[pick_out(p, teams) for p in picks],
        on_the_clock=clock.number if clock else None,
        my_team_id=user_team,
        my_next_pick=next((p.number for p in picks
                           if p.player_id is None and p.team_id == user_team), None),
        prospects=prospects, scouting_left=scouting_left(db, league.id, year),
        roster_count=roster_count, roster_max=ROSTER_MAX)
