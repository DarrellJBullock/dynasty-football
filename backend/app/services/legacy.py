"""Legacy (docs/design/staff-and-legacy.md §4): the Hall of Fame, retired numbers, and each
team's record book.

Each offseason (`induct`, from offseason.advance) the retired players who've waited long
enough are scored (domain/legacy.py) from their careers in the league's box scores, the
best get in, and the ballot is kept to show who came close. An AI team retires its
inductee's number at once; a member's team decides (`retire_number`).
"""

from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain import legacy as rules
from app.models import (
    Award,
    Game,
    HallOfFameVote,
    League,
    Player,
    PlayerGameStats,
    RetiredNumber,
    Season,
    Team,
)
from app.schemas import (
    HallOfFameOut,
    HallOfFamer,
    RetiredNumberOut,
    TeamRecordsOut,
)
from app.services.errors import RosterError
from app.services.history import STAT_FIELDS, records
from app.services.members import human_team_ids
from app.services.notifications import notify_members, notify_team
from app.services.serializers import team_summary


def careers(db: Session, league: League) -> tuple[dict[int, rules.Career], dict[int, int]]:
    """Every player's regular-season career in the league, and the team he played the most
    games for. One pass over the box scores, by player, season and team."""
    weeks = dict(db.execute(
        select(Game.season_id, func.max(Game.week)).join(Season)
        .where(Season.league_id == league.id, Game.stage == "regular")
        .group_by(Game.season_id)).all())
    champions = dict(db.execute(select(Season.id, Season.champion_team_id)
                                .where(Season.league_id == league.id)).all())
    rows = db.execute(
        select(PlayerGameStats.player_id, Game.season_id, PlayerGameStats.team_id,
               func.count(PlayerGameStats.id).label("games"),
               *[func.sum(getattr(PlayerGameStats, f)).label(f) for f in STAT_FIELDS])
        .join(Game, Game.id == PlayerGameStats.game_id).join(Season, Season.id == Game.season_id)
        .where(Season.league_id == league.id, Game.stage == "regular")
        .group_by(PlayerGameStats.player_id, Game.season_id, PlayerGameStats.team_id)
    ).mappings().all()
    positions = dict(db.execute(select(Player.id, Player.position)
                                .where(Player.league_id == league.id)).all())
    out: dict[int, rules.Career] = {}
    season_games: dict[tuple[int, int], int] = defaultdict(int)
    team_games: dict[int, Counter] = defaultdict(Counter)
    titles: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        pid = row["player_id"]
        career = out.setdefault(pid, rules.Career(pid, positions[pid]))
        career.games += row["games"]
        for f in STAT_FIELDS:
            career.stats[f] = career.stats.get(f, 0) + (row[f] or 0)
        season_games[(pid, row["season_id"])] += row["games"]
        team_games[pid][row["team_id"]] += row["games"]
        if champions.get(row["season_id"]) == row["team_id"]:
            titles[pid].add(row["season_id"])
    for (pid, season_id), games in season_games.items():
        if games >= rules.REGULAR_SHARE * weeks.get(season_id, 1):
            out[pid].regular_seasons += 1
    for pid, seasons in titles.items():
        out[pid].titles = len(seasons)
    for pid, award in db.execute(select(Award.player_id, Award.award).join(Season)
                                 .where(Season.league_id == league.id)):
        if pid in out:
            out[pid].awards[award] = out[pid].awards.get(award, 0) + 1
    primary = {pid: max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
               for pid, counts in team_games.items()}
    return out, primary


def induct(db: Session, league: League, year: int) -> list[HallOfFameVote]:
    """This year's Hall of Fame vote: who gets in, and the near misses. Once a year."""
    if db.scalar(select(HallOfFameVote.id).where(HallOfFameVote.league_id == league.id,
                                                 HallOfFameVote.year == year).limit(1)):
        return []
    members = set(db.scalars(select(HallOfFameVote.player_id).where(
        HallOfFameVote.league_id == league.id, HallOfFameVote.inducted)))
    eligible_ids = set(db.scalars(select(Player.id).where(
        Player.league_id == league.id, Player.retired_year.is_not(None),
        Player.retired_year <= year - rules.ELIGIBLE_AFTER))) - members
    if not eligible_ids:
        return []
    everyone, primary = careers(db, league)
    ranks = rules.percentiles(list(everyone.values()))
    scored = [(c, rules.score(c, ranks[c.player_id])) for pid, c in everyone.items()
              if pid in eligible_ids]
    inducted, misses = rules.ballot(scored)
    by_id = {c.player_id: (c, s) for c, s in scored}
    votes = []
    for pid in inducted + misses:
        career, score = by_id[pid]
        vote = HallOfFameVote(league_id=league.id, year=year, player_id=pid,
                              team_id=primary.get(pid), score=round(score, 1),
                              inducted=pid in inducted, case=rules.case(career))
        db.add(vote)
        votes.append(vote)
    db.flush()
    _honor(db, league, year, [v for v in votes if v.inducted])
    return votes


def _honor(db: Session, league: League, year: int, inductees: list[HallOfFameVote]) -> None:
    """AI teams retire their inductees' numbers; members hear about the class, and a
    manager whose team the inductee defined is asked about his number."""
    if not inductees:
        return
    humans = human_team_ids(db, league.id)
    names = []
    for vote in inductees:
        player = vote.player
        names.append(f"{player.position} {player.full_name}")
        if vote.team_id is None or player.jersey_number is None:
            continue
        if vote.team_id in humans:
            notify_team(db, vote.team_id, "legacy",
                        f"{player.full_name} is in the Hall of Fame",
                        f"Retire his number {player.jersey_number}? You can on the Records page.",
                        f"/records?team={vote.team_id}", key=f"retire:{vote.id}")
        else:
            _retire(db, vote.team_id, player, year)
    notify_members(db, league.id, "legacy", f"The {year} Hall of Fame class",
                   ", ".join(names) + ".", "/hall-of-fame", key=f"hall:{league.id}:{year}")


def _retire(db: Session, team_id: int, player: Player, year: int) -> RetiredNumber | None:
    taken = db.scalar(select(RetiredNumber.id).where(RetiredNumber.team_id == team_id,
                                                    RetiredNumber.number == player.jersey_number))
    if taken:
        return None  # (someone else's already)
    retired = RetiredNumber(team_id=team_id, number=player.jersey_number, player_id=player.id,
                            year=year)
    db.add(retired)
    db.flush()
    return retired


def retire_number(db: Session, team: Team, player_id: int) -> RetiredNumber:
    """A team retires a former player's number: a retired player who played for it."""
    player = db.get(Player, player_id)
    if player is None or player.league_id != team.league_id or player.retired_year is None:
        raise RosterError("Only a retired player's number can be retired.")
    played = db.scalar(select(PlayerGameStats.id).where(PlayerGameStats.player_id == player.id,
                                                        PlayerGameStats.team_id == team.id)
                       .limit(1))
    if not played:
        raise RosterError(f"{player.full_name} never played for the {team.nickname}.")
    if player.jersey_number is None:
        raise RosterError(f"{player.full_name} has no number to retire.")
    season = db.scalar(select(func.max(Season.year)).where(Season.league_id == team.league_id))
    retired = _retire(db, team.id, player, season or 0)
    if retired is None:
        raise RosterError(f"The {team.nickname} already retired number {player.jersey_number}.")
    return retired


# ---------- views ----------

def _famer(vote: HallOfFameVote) -> HallOfFamer:
    player = vote.player
    return HallOfFamer(player_id=player.id, name=player.full_name, position=player.position,
                       year=vote.year, team=team_summary(vote.team) if vote.team else None,
                       score=vote.score, case=vote.case, inducted=vote.inducted,
                       retired_year=player.retired_year)


def _retired_out(row: RetiredNumber, team: Team) -> RetiredNumberOut:
    return RetiredNumberOut(team=team_summary(team), number=row.number,
                            player_id=row.player_id, name=row.player.full_name, year=row.year)


def hall_of_fame(db: Session, league: League) -> HallOfFameOut:
    votes = db.scalars(select(HallOfFameVote).where(HallOfFameVote.league_id == league.id)
                       .options(selectinload(HallOfFameVote.player),
                                selectinload(HallOfFameVote.team))
                       .order_by(HallOfFameVote.year.desc(), HallOfFameVote.score.desc(),
                                 HallOfFameVote.player_id)).all()
    latest = max((v.year for v in votes), default=None)
    teams = {t.id: t for t in league.teams}
    numbers = db.scalars(select(RetiredNumber).where(RetiredNumber.team_id.in_(teams))
                         .options(selectinload(RetiredNumber.player))
                         .order_by(RetiredNumber.team_id, RetiredNumber.number)).all()
    return HallOfFameOut(
        members=[_famer(v) for v in votes if v.inducted],
        ballot_year=latest,
        near_misses=[_famer(v) for v in votes if v.year == latest and not v.inducted],
        retired_numbers=[_retired_out(r, teams[r.team_id]) for r in numbers],
        eligible_after=rules.ELIGIBLE_AFTER, bar=rules.BAR)


def team_records(db: Session, team: Team, can_retire: bool) -> TeamRecordsOut:
    """A team's record book: its single-game, single-season and career records (as the
    team), its Hall of Famers and retired numbers, and, for its manager, former players
    whose numbers it could retire."""
    league = db.get(League, team.league_id)
    numbers = db.scalars(select(RetiredNumber).where(RetiredNumber.team_id == team.id)
                         .options(selectinload(RetiredNumber.player))
                         .order_by(RetiredNumber.number)).all()
    famers = db.scalars(select(HallOfFameVote).where(
        HallOfFameVote.team_id == team.id, HallOfFameVote.inducted)
        .options(selectinload(HallOfFameVote.player), selectinload(HallOfFameVote.team))
        .order_by(HallOfFameVote.year)).all()
    candidates = []
    if can_retire:
        taken = {r.number for r in numbers}
        former = db.scalars(select(Player).where(
            Player.retired_year.is_not(None), Player.jersey_number.is_not(None),
            Player.id.in_(select(PlayerGameStats.player_id)
                          .where(PlayerGameStats.team_id == team.id)))
            .order_by(Player.overall.desc(), Player.id).limit(40)).all()
        honored = {f.player_id for f in famers}
        candidates = sorted(
            ({"player_id": p.id, "name": p.full_name, "position": p.position,
              "number": p.jersey_number, "hall_of_fame": p.id in honored}
             for p in former if p.jersey_number not in taken),
            key=lambda c: (not c["hall_of_fame"], c["name"]))
    return TeamRecordsOut(team=team_summary(team), records=records(db, league, team.id),
                          hall_of_famers=[_famer(f) for f in famers],
                          retired_numbers=[_retired_out(r, team) for r in numbers],
                          retire_candidates=candidates)
