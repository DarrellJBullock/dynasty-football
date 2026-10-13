"""The draft: classes of fictional prospects, scouting, draft order, picks, and what
happens after (undrafted free agents, roster cut-downs).

A class for year Y is generated (deterministically) when it's first needed: the franchise
scouts it during season Y-1, and it's drafted in season Y after free agency (phase
"draft"). Then the season moves to the preseason.
"""

import hashlib
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.domain import staff as staff_rules
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
    ROSTER_TEMPLATE,
    SPECIAL_TEAMS,
    Position,
    available_jersey,
)
from app.domain.ratings import clamp_rating
from app.models import Contract, DraftPick, Game, League, Player, Season, Team
from app.schemas import DraftOut, DraftPickOut, DraftResult, ProspectRow
from app.seed.generator import SPECIALIST_OFFSET, _development_trait, make_player
from app.services import cap as cap_rules
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.members import human_team_ids
from app.services.notifications import notify_team
from app.services.retired import league_retired, retired_numbers
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


def projection(league_id: int, player: Player, scale: float = 1.0) -> tuple[int, int]:
    """A team's view of a prospect: (OVR, potential), exact once scouted. `scale`: how far
    off its scout's projections are, against an average scout's (domain/staff.py)."""
    if player.scouted:
        return player.overall, player.potential
    noise = scout_noise(league_id, prospect_key(player)) * scale
    return clamp_rating(player.overall + noise), clamp_rating(player.potential + noise)


def prospect_row(league_id: int, player: Player, scale: float = 1.0) -> ProspectRow:
    ovr, potential = projection(league_id, player, scale)
    spread = 0 if player.scouted else PROJECTION_RANGE
    return ProspectRow(
        id=player.id, full_name=player.full_name, position=player.position, age=player.age,
        college=player.college, height_in=player.height_in, weight_lb=player.weight_lb,
        projected=ovr, low=ovr - spread, high=ovr + spread, grade=potential_grade(potential),
        scouted=player.scouted, overall=player.overall if player.scouted else None,
        potential=player.potential if player.scouted else None)


def scouting_left(db: Session, league_id: int, year: int,
                  reports: int = SCOUTING_REPORTS) -> int:
    used = db.scalar(select(func.count(Player.id)).where(
        Player.league_id == league_id, Player.draft_year == year, Player.scouted)) or 0
    return max(0, reports - used)


def _scout(db: Session, league_id: int, team_id: int | None):
    """A team's scout, as staff rules see him (None: no team, so an average view)."""
    from app.services import staff  # (staff builds on the season services)

    if team_id is None:
        return None
    crew = staff.by_team(db, db.get(League, league_id))
    return staff.coach(crew.get(team_id, {}).get("scout"))


def scouting(db: Session, league_id: int, team_id: int | None) -> tuple[float, int]:
    """(projection scale, scouting reports a class) for a team, from its scout and its
    scouting department."""
    from app.services import facilities  # (it builds on the staff budget)

    scout = _scout(db, league_id, team_id)
    level = facilities.levels(db, db.get(League, league_id)).get(team_id, {}).get(
        "scouting", 1) if team_id is not None else 1
    return (staff_rules.scout_scale(scout, level),
            staff_rules.scouting_reports(SCOUTING_REPORTS, scout, level))


def scout(db: Session, player: Player, team_id: int | None = None) -> ProspectRow:
    season = current_season(db, player.league_id)
    if not player.is_prospect or player.draft_year != class_year(db, season):
        raise RosterError(f"{player.full_name} isn't in the draft class you're scouting.")
    if not player.scouted:
        scale, reports = scouting(db, player.league_id, team_id)
        if scouting_left(db, player.league_id, player.draft_year, reports) <= 0:
            raise RosterError(f"No scouting reports left ({reports} per class).")
        player.scouted = True
        db.flush()
    return prospect_row(player.league_id, player, scouting(db, player.league_id, team_id)[0])


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
    slot = {team_id: index for index, team_id in enumerate(order)}
    for pick in ensure_picks(db, league, season.year):
        # Picks follow the team they came from, wherever they've been traded since.
        pick.season_id = season.id
        pick.number = (pick.round - 1) * len(order) + slot[pick.original_team_id] + 1
    season.phase = "draft"
    db.flush()


def ensure_picks(db: Session, league: League, year: int) -> list[DraftPick]:
    """Every team's picks in the `year` draft (created once, owned by the team at first)."""
    picks = list(db.scalars(select(DraftPick).where(DraftPick.league_id == league.id,
                                                    DraftPick.year == year)))
    if not picks:
        for team_id in db.scalars(select(Team.id).where(Team.league_id == league.id)
                                  .order_by(Team.id)):
            for round_number in range(1, ROUNDS + 1):
                pick = DraftPick(league_id=league.id, year=year, round=round_number,
                                 original_team_id=team_id, team_id=team_id)
                db.add(pick)
                picks.append(pick)
        db.flush()
    return picks


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
    # (with the players picked, for the board: one query each, not one per pick)
    return list(db.scalars(select(DraftPick).where(DraftPick.season_id == season.id)
                           .order_by(DraftPick.number)
                           .options(selectinload(DraftPick.player).options(
                               selectinload(Player.ratings), selectinload(Player.contracts)))))


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
    player.contracts.append(Contract.signed(team_id, season.year, years, salary))
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
        for team_id, numbers in league_retired(db, season.league_id).items():
            self.jerseys[team_id] |= numbers  # (never reissued)

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


def _auto_pick(season: Season, pick: DraftPick, board: _Board, user: bool,
               scale: float = 1.0) -> Player:
    """AI teams value prospects by their own (noisy) read of OVR and potential; the
    franchise's auto-pick uses its scouting projection. Both favour positions of need."""
    league_id = season.league_id
    if not board.available:
        raise RosterError("No prospects left.")
    needs = board.needs(season, pick.team_id)
    rng = _rng("draft-pick", league_id, season.year, pick.number)
    if user:
        def value(p: Player) -> float:
            ovr, potential = projection(league_id, p, scale)
            return ai_value(rng, ovr, potential, p.position in needs)
    else:
        def value(p: Player) -> float:
            return ai_value(rng, p.overall, p.potential, p.position in needs)
    candidates = sorted(board.available, key=lambda p: -(p.overall + p.potential))[:CANDIDATES]
    return max(candidates, key=lambda p: (value(p), -p.id))


def user_pick(db: Session, league: League, player_id: int, team_id: int | None) -> DraftPick:
    """`team_id`'s manager makes the pick they're on the clock for."""
    season = current_season(db, league.id)
    pick = on_the_clock(db, season)
    if pick is None:
        raise RosterError("The draft isn't live.")
    if team_id is None or pick.team_id != team_id:
        raise RosterError("You're not on the clock.")
    player = db.get(Player, player_id)
    if (player is None or player.league_id != league.id or not player.is_prospect
            or player.draft_year != season.year):
        raise RosterError("That player isn't available.")
    _make_pick(db, season, pick, player, _Board(db, season))
    db.flush()
    if _clocked(db, season):  # (AI teams pick at once, up to the next manager)
        season.pick_clock_started_at = None
        play(db, season, "my_pick")
    return pick


# ---------- the draft clock (several managers: docs/design/leagues-with-friends.md §4) ----------

def _clocked(db: Session, season: Season) -> bool:
    """Picks are on a clock when more than one member runs a team."""
    return len(human_team_ids(db, season.league_id)) > 1


def _clock_words(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes"
    return "a day" if minutes == 1440 else f"{minutes // 60} hour{'s' if minutes > 60 else ''}"


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def clock_ends_at(db: Session, season: Season) -> datetime | None:
    """When the manager on the clock runs out of time (None: no clock running)."""
    if season.phase != "draft" or season.pick_clock_started_at is None:
        return None
    return (_as_utc(season.pick_clock_started_at)
            + timedelta(minutes=season.league.draft_clock_minutes))


def run_clock(db: Session, season: Season, now: datetime | None = None) -> list[DraftPick]:
    """If the manager on the clock ran out of time, pick for them (by their needs, as
    auto-pick does) and let AI teams pick up to the next manager, whose clock starts.
    Returns the picks made."""
    ends = clock_ends_at(db, season)
    if ends is None or (now or datetime.now(UTC)) < ends:
        return []
    pick = on_the_clock(db, season)
    if pick is None:
        season.pick_clock_started_at = None
        return []
    board = _Board(db, season)
    _make_pick(db, season, pick, _auto_pick(season, pick, board, user=True,
                                            scale=scouting(db, season.league_id,
                                                           pick.team_id)[0]), board)
    season.pick_clock_started_at = None
    db.flush()
    return [pick, *play(db, season, "my_pick")]


def play(db: Session, season: Season, until: str, autopilot: bool = False) -> list[DraftPick]:
    """Make picks until a member's team is on the clock (`my_pick`) or to the end (`end`,
    auto-picking for members' teams by their needs); after the last pick the draft wraps
    up."""
    if season.phase != "draft":
        raise RosterError("The draft isn't live.")
    humans = human_team_ids(db, season.league_id)
    board = _Board(db, season)
    remaining = [p for p in _picks(db, season) if p.player_id is None]
    made: list[DraftPick] = []
    for pick in remaining:
        mine = pick.team_id in humans
        if mine and until == "my_pick":
            if (made or season.pick_clock_started_at is None) and _clocked(db, season):
                season.pick_clock_started_at = datetime.now(UTC)  # (their clock starts)
                notify_team(db, pick.team_id, "your_pick", "You're on the clock",
                            f"Round {pick.round}, pick {pick.number} of the {season.year} draft. "
                            f"You have {_clock_words(season.league.draft_clock_minutes)}.",
                            "/draft", key=f"pick:{pick.id}")
            break
        scale = scouting(db, season.league_id, pick.team_id)[0] if mine else 1.0
        _make_pick(db, season, pick, _auto_pick(season, pick, board, user=mine, scale=scale),
                   board)
        made.append(pick)
    db.flush()
    if on_the_clock(db, season) is None:
        season.pick_clock_started_at = None
        _finish(db, season, autopilot)
    return made


def _finish(db: Session, season: Season, autopilot: bool = False) -> None:
    """Fill the spots teams still lost — the best undrafted prospect at the position, then
    the best one left, then a veteran free agent on a one-year minimum deal — make the
    rest of the class free agents, cut AI teams down to 53, and start the preseason. On
    autopilot (sim ahead) the franchise is cut down and fit under the cap like the rest."""
    league_id = season.league_id
    log = season.offseason_log
    humans = set() if autopilot else human_team_ids(db, league_id)
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
        while lost and len(roster) < team.league.roster_max and (undrafted or veterans):
            player = (next((p for p in undrafted if p.position == lost[0]), None)
                      or (undrafted[0] if undrafted else veterans[0]))
            fills_own_spot = player.position in lost  # (then _join crosses it off)
            taken = {p.jersey_number for p in roster} | retired_numbers(db, team.id)
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
        if team.id in humans:
            continue  # (members cut their own rosters)
        roster = _roster(db, team.id)
        for player in sorted(roster, key=lambda p: (p.overall, -p.age, p.id))[
                :max(0, len(roster) - team.league.roster_max)]:
            _release(db, player, season)
            cuts.append({"player": player.id, "team": team.id})
        _fit_under_cap(db, season, team, cap, veterans, cuts)
    season.phase = "preseason"
    flag_modified(season, "offseason_log")
    db.flush()
    # Jobs still open (a member's team that didn't hire) get an interim hire.
    from app.services import carousel  # (it builds on the season services)

    carousel.fill_vacancies(db, season.league, season.year)


def _fit_under_cap(db: Session, season: Season, team: Team, cap: int,
                   veterans: list[Player], cuts: list[dict]) -> None:
    """Rookie deals can push a team over the cap: release the most overpaid veterans
    (salary furthest above market value; never this year's picks), each replaced by a
    free agent on a one-year minimum deal, until it fits."""
    roster = _roster(db, team.id)
    payroll = (sum(c.salary for p in roster if (c := p.active_contract))
               + cap_rules.dead_money_for(db, team.id, season.year))
    # Releasing saves his salary but leaves the rest of his bonus as dead money.
    def saving(p: Player) -> int:
        return p.active_contract.salary - cap_rules.release_cost(p.active_contract, season.year)

    candidates = sorted(
        (p for p in roster if p.draft_year != season.year and p.active_contract
         and saving(p) > MIN_SALARY),
        key=lambda p: (-(p.active_contract.salary
                         - market_salary(Position(p.position), p.overall)), p.id))
    for player in candidates:
        if payroll <= cap:
            break
        payroll -= saving(player)
        _release(db, player, season)
        cuts.append({"player": player.id, "team": team.id})
        roster.remove(player)
        if veterans:
            replacement = veterans.pop(0)
            _join(season, replacement, team.id, MIN_SALARY, 1,
                  {p.jersey_number for p in roster})
            roster.append(replacement)
            payroll += MIN_SALARY


def _release(db: Session, player: Player, season: Season) -> None:
    cap_rules.charge(db, player, player.active_contract, cap_rules.cap_year(season), "released")
    for contract in player.contracts:
        contract.is_active = False
    remove_player(db, player)
    player.team_id = None


def cut_down(db: Session, team: Team) -> list[Player]:
    """Release the lowest-rated players (the cheapest to cut among equals) until the
    roster is at the league's limit."""
    season = current_season(db, team.league_id)
    year = cap_rules.cap_year(season)
    roster = _roster(db, team.id)
    excess = sorted(roster, key=lambda p: (p.overall, cap_rules.release_cost(
        p.active_contract, year), -p.age, p.id))[:max(0, len(roster) - team.league.roster_max)]
    for player in excess:
        _release(db, player, season)
    db.flush()
    return excess


# ---------- view ----------


def pick_out(pick: DraftPick, teams: int) -> DraftPickOut:
    return DraftPickOut(round=pick.round, number=pick.number,
                        pick_in_round=pick.number - (pick.round - 1) * teams,
                        team=team_summary(pick.team),
                        original_team=team_summary(pick.original_team)
                        if pick.original_team_id != pick.team_id else None,
                        player=player_summary(pick.player) if pick.player else None)


def team_count(db: Session, league_id: int) -> int:
    return db.scalar(select(func.count(Team.id)).where(Team.league_id == league_id)) or 0


def draft_view(db: Session, league: League, user_team: int | None = None) -> DraftOut:
    """The draft as `user_team`'s manager sees it (their picks and roster)."""
    from app.services.season import season_view

    season = current_season(db, league.id)
    year = class_year(db, season)
    ensure_class(db, league, year)
    run_clock(db, season)  # (a clock that ran out while nobody was looking)
    picks = _picks(db, season) if year == season.year else []
    clock = on_the_clock(db, season)
    status = "live" if clock else "complete" if picks else "upcoming"
    scale, reports = scouting(db, league.id, user_team)
    prospects = sorted((prospect_row(league.id, p, scale)
                        for p in _prospects(db, league.id, year)),
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
        prospects=prospects, scouting_left=scouting_left(db, league.id, year, reports),
        roster_count=roster_count, roster_max=league.roster_max,
        clock_ends_at=clock_ends_at(db, season) if clock else None)


def play_result(db: Session, season: Season, picks: list[DraftPick]) -> DraftResult:
    """What a run of picks did."""
    from app.services.season import season_view

    teams = team_count(db, season.league_id)
    return DraftResult(season=season_view(db, season), picks=[pick_out(p, teams) for p in picks])
