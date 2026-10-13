"""League history: season awards, the season-by-season archive, records, and careers.

Everything is derived from stored regular-season box scores; awards are decided once, when
a season's champion is crowned (and backfilled for seasons finished before awards
existed).
"""

from collections import defaultdict
from dataclasses import fields

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.awards import AWARDS, Candidate, choose, summary
from app.models import (
    Award,
    Game,
    HallOfFameVote,
    League,
    Player,
    PlayerGameStats,
    PlayoffSeed,
    RetiredNumber,
    Season,
    Team,
)
from app.schemas import (
    AwardOut,
    CareerOut,
    CareerSeason,
    HistoryOut,
    Record,
    RecordCategory,
    RecordRow,
    SeasonHistory,
)
from app.services import playoffs
from app.services.serializers import team_summary
from app.services.standings import compute_records
from app.sim.stats import PlayerLine

STAT_FIELDS = [f.name for f in fields(PlayerLine) if not f.name.endswith("_long")]
RECORD_CATEGORIES = [
    ("passing_yards", "Passing yards", "pass_yds"), ("passing_td", "Passing TD", "pass_td"),
    ("rushing_yards", "Rushing yards", "rush_yds"), ("rushing_td", "Rushing TD", "rush_td"),
    ("receiving_yards", "Receiving yards", "rec_yds"), ("receptions", "Receptions", "receptions"),
    ("receiving_td", "Receiving TD", "rec_td"), ("tackles", "Tackles", "tackles"),
    ("sacks", "Sacks", "sacks"), ("interceptions", "Interceptions", "interceptions"),
]
RECORDS_SHOWN = 5


def _regular(stmt, league_id: int):
    return (stmt.join(Game, Game.id == PlayerGameStats.game_id)
            .join(Season, Season.id == Game.season_id)
            .where(Season.league_id == league_id, Game.stage == "regular"))


def season_lines(db: Session, season: Season) -> dict[int, tuple[int, dict[str, int], int]]:
    """player_id -> (games, regular-season totals, team he played most games for)."""
    sums = [func.sum(getattr(PlayerGameStats, f)).label(f) for f in STAT_FIELDS]
    rows = db.execute(
        select(PlayerGameStats.player_id, PlayerGameStats.team_id,
               func.count(PlayerGameStats.id).label("games"), *sums)
        .join(Game, Game.id == PlayerGameStats.game_id)
        .where(Game.season_id == season.id, Game.stage == "regular")
        .group_by(PlayerGameStats.player_id, PlayerGameStats.team_id)).mappings().all()
    lines: dict[int, tuple[int, dict[str, int], int]] = {}
    most: dict[int, int] = {}
    for row in rows:
        pid = row["player_id"]
        games, stats, team = lines.get(pid, (0, defaultdict(int), row["team_id"]))
        for f in STAT_FIELDS:
            stats[f] += row[f] or 0
        if row["games"] > most.get(pid, -1):
            most[pid], team = row["games"], row["team_id"]
        lines[pid] = (games + row["games"], stats, team)
    return {pid: (games, dict(stats), team) for pid, (games, stats, team) in lines.items()}


def _rookies(db: Session, season: Season, player_ids: list[int]) -> set[int]:
    """First-year pros that season. `years_pro` counts up at every rollover a player is
    active for, so his experience back then is today's minus the rollovers since (which
    stop the offseason he retired)."""
    if not player_ids:
        return set()
    latest = db.scalar(select(func.max(Season.year)).where(
        Season.league_id == season.league_id))
    rookies = set()
    for player in db.scalars(select(Player).where(Player.id.in_(player_ids))):
        if player.draft_year is not None and player.draft_year > season.year:
            continue  # not in the league yet
        last = min(latest, player.retired_year + 1) if player.retired_year else latest
        if player.years_pro - (last - season.year) <= 0:
            rookies.add(player.id)
    return rookies


def award_season(db: Session, season: Season) -> None:
    """Decide the season's awards (once, after the champion is crowned)."""
    if not season.champion_team_id or db.scalar(
            select(Award.id).where(Award.season_id == season.id).limit(1)):
        return
    lines = season_lines(db, season)
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(lines)))}
    wins = {team_id: r.wins for team_id, r in compute_records(
        db, season, list({team for _, _, team in lines.values()})).items()}
    rookies = _rookies(db, season, list(lines))
    candidates = [Candidate(pid, players[pid].position, games, stats, wins.get(team, 0),
                            pid in rookies)
                  for pid, (games, stats, team) in lines.items() if pid in players]
    weeks = playoffs.regular_week_count(db, season.id)
    for award, winner in choose(candidates, weeks).items():
        _, stats, team = lines[winner.player_id]
        db.add(Award(season_id=season.id, award=award, player_id=winner.player_id,
                     team_id=team, summary=summary(winner.position, stats)))
    db.flush()


def ensure_awards(db: Session, league: League) -> None:
    for season in league.seasons:
        award_season(db, season)


def _award_out(award: Award, year: int) -> AwardOut:
    return AwardOut(award=award.award, label=AWARDS[award.award], year=year,
                    player_id=award.player_id, name=award.player.full_name,
                    position=award.player.position,
                    team=team_summary(award.team) if award.team else None,
                    summary=award.summary)


# ---------- the archive ----------


def _final(db: Session, season: Season) -> Game | None:
    return db.scalar(select(Game).where(Game.season_id == season.id, Game.stage == "playoff",
                                        Game.status == "final")
                     .order_by(Game.playoff_round.desc(), Game.id.desc()).limit(1))


def _franchise_result(db: Session, season: Season, team_id: int) -> str:
    if season.champion_team_id == team_id:
        return "Won the championship"
    games = db.scalars(select(Game).where(
        Game.season_id == season.id, Game.stage == "playoff", Game.status == "final",
        (Game.home_team_id == team_id) | (Game.away_team_id == team_id))
        .order_by(Game.playoff_round)).all()
    lost = next((g for g in games if (g.home_score > g.away_score) != (g.home_team_id == team_id)),
                None)
    if lost is not None:
        return f"Lost in the {playoffs.round_name(db, season, lost.playoff_round)}"
    if season.phase in ("playoffs",) and db.scalar(select(PlayoffSeed.id).where(
            PlayoffSeed.season_id == season.id, PlayoffSeed.team_id == team_id)):
        return "In the playoffs"
    if season.phase in ("playoffs", "offseason"):
        return "Missed the playoffs"
    return "Season in progress" if season.phase == "regular_season" else "Not started"


def history_view(db: Session, league: League, team_id: int | None = None) -> HistoryOut:
    """The league's history, with `team_id`'s (the viewer's) seasons marked."""
    return HistoryOut(seasons=season_histories(db, league, team_id=team_id),
                      records=records(db, league))


def season_histories(db: Session, league: League, years: range | None = None,
                     team_id: int | None = None) -> list[SeasonHistory]:
    """Each season (or those in `years`), latest first: champion, runner-up, awards, and
    `team_id`'s record and result (the viewer's team)."""
    ensure_awards(db, league)
    seasons = sorted((s for s in league.seasons if years is None or s.year in years),
                     key=lambda s: -s.year)
    awards: dict[int, list[Award]] = defaultdict(list)
    for award in db.scalars(select(Award).where(Award.season_id.in_([s.id for s in seasons]))
                            .options(selectinload(Award.player))):
        awards[award.season_id].append(award)
    order = list(AWARDS)
    out = []
    for season in seasons:
        final = _final(db, season) if season.champion_team_id else None
        runner_up = None
        if final is not None:
            loser = final.away_team if final.home_team_id == season.champion_team_id \
                else final.home_team
            runner_up = team_summary(loser)
        record = compute_records(db, season, [team_id])[team_id] if team_id else None
        out.append(SeasonHistory(
            season_id=season.id, year=season.year, phase=season.phase,
            complete=season.champion_team_id is not None,
            champion=team_summary(season.champion) if season.champion else None,
            runner_up=runner_up,
            awards=[_award_out(a, season.year) for a in
                    sorted(awards[season.id], key=lambda a: order.index(a.award))],
            franchise_record=Record(wins=record.wins, losses=record.losses,
                                    ties=record.ties) if record else None,
            franchise_result=_franchise_result(db, season, team_id) if team_id else ""))
    return out


# ---------- records ----------


def records(db: Session, league: League, team_id: int | None = None) -> list[RecordCategory]:
    """Single-season and career leaders for each record category (only games for
    `team_id`, for a team's record book). One pass sums every category by player and
    season (rather than two scans of the league's stat lines per category); ties go to the
    earlier season, then the lower player id. A team's book adds single-game records."""
    stats = [stat for _, _, stat in RECORD_CATEGORIES]
    stmt = _regular(
        select(PlayerGameStats.player_id, Season.year,
               func.count(PlayerGameStats.id).label("games"),
               *[func.sum(getattr(PlayerGameStats, stat)).label(stat) for stat in stats]),
        league.id)
    if team_id is not None:
        stmt = stmt.where(PlayerGameStats.team_id == team_id)
    rows = db.execute(stmt.group_by(PlayerGameStats.player_id, Season.year)).mappings().all()
    games = _single_games(db, league, team_id, stats) if team_id is not None else {}
    careers: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        totals = careers[row["player_id"]]
        totals["games"] += row["games"]
        for stat in stats:
            totals[stat] += row[stat] or 0
    tops = {}
    for _, _, stat in RECORD_CATEGORIES:
        single = sorted(((row[stat], row["year"], row["player_id"], row["games"])
                         for row in rows if (row[stat] or 0) > 0),
                        key=lambda r: (-r[0], r[1], r[2]))[:RECORDS_SHOWN]
        career = sorted(((totals[stat], pid, totals["games"])
                         for pid, totals in careers.items() if totals[stat] > 0),
                        key=lambda r: (-r[0], r[1]))[:RECORDS_SHOWN]
        tops[stat] = (single, career)
    ids = {r[2] for single, _ in tops.values() for r in single} | {
        r[1] for _, career in tops.values() for r in career} | {
        r[2] for best in games.values() for r in best}
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(ids))
                                           .options(selectinload(Player.team)))}
    return [
        RecordCategory(
            key=key, label=label,
            single_season=[_record_row(players[pid], value, games, year)
                           for value, year, pid, games in tops[stat][0]],
            career=[_record_row(players[pid], value, games, None)
                    for value, pid, games in tops[stat][1]],
            single_game=[_record_row(players[pid], value, 1, year)
                         for value, year, pid in games.get(stat, [])])
        for key, label, stat in RECORD_CATEGORIES
    ]


def _single_games(db: Session, league: League, team_id: int,
                  stats: list[str]) -> dict[str, list[tuple[int, int, int]]]:
    """The team's best single games in each category: stat -> [(value, year, player)]."""
    best = {}
    for stat in stats:
        column = getattr(PlayerGameStats, stat)
        best[stat] = [(value, year, pid) for value, year, pid in db.execute(_regular(
            select(column, Season.year, PlayerGameStats.player_id), league.id)
            .where(PlayerGameStats.team_id == team_id, column > 0)
            .order_by(column.desc(), Season.year, PlayerGameStats.player_id)
            .limit(RECORDS_SHOWN))]
    return best


def _record_row(player: Player, value: int, games: int, year: int | None) -> RecordRow:
    return RecordRow(player_id=player.id, name=player.full_name, position=player.position,
                     team=player.team.abbreviation if player.team else None, year=year,
                     value=int(value), games=games, retired=player.retired_year is not None)


# ---------- careers ----------


def career(db: Session, player: Player) -> CareerOut:
    seasons = db.scalars(select(Season).where(Season.league_id == player.league_id)
                         .order_by(Season.year)).all()
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.league_id == player.league_id))}
    rows, totals, games = [], defaultdict(int), 0
    for season in seasons:
        line = _player_season(db, season, player.id)
        if line is None:
            continue
        season_games, stats, team_id = line
        rows.append(CareerSeason(year=season.year, team=team_summary(teams[team_id]),
                                 games=season_games,
                                 stats={k: v for k, v in stats.items() if v}))
        games += season_games
        for k, v in stats.items():
            totals[k] += v
    awards = db.execute(select(Award, Season.year).join(Season, Season.id == Award.season_id)
                        .where(Award.player_id == player.id).order_by(Season.year)).all()
    inducted = db.scalar(select(HallOfFameVote.year).where(
        HallOfFameVote.player_id == player.id, HallOfFameVote.inducted))
    retired_by = db.scalars(select(Team.nickname).join(
        RetiredNumber, RetiredNumber.team_id == Team.id)
        .where(RetiredNumber.player_id == player.id).order_by(Team.nickname)).all()
    return CareerOut(player_id=player.id, seasons=rows, games=games,
                     totals={k: v for k, v in totals.items() if v},
                     awards=[_award_out(a, year) for a, year in awards],
                     hall_of_fame=inducted, retired_by=list(retired_by))


def _player_season(db: Session, season: Season, player_id: int):
    sums = [func.sum(getattr(PlayerGameStats, f)).label(f) for f in STAT_FIELDS]
    rows = db.execute(
        select(PlayerGameStats.team_id, func.count(PlayerGameStats.id).label("games"), *sums)
        .join(Game, Game.id == PlayerGameStats.game_id)
        .where(Game.season_id == season.id, Game.stage == "regular",
               PlayerGameStats.player_id == player_id)
        .group_by(PlayerGameStats.team_id)).mappings().all()
    if not rows:
        return None
    stats: dict[str, int] = defaultdict(int)
    for row in rows:
        for f in STAT_FIELDS:
            stats[f] += row[f] or 0
    main = max(rows, key=lambda r: r["games"])
    return sum(r["games"] for r in rows), dict(stats), main["team_id"]
