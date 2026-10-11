"""Season statistics aggregated from per-game stats rows: leaders, player seasons, teams."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import Game, Player, PlayerGameStats, Season, Team, TeamGameStats
from app.schemas import (
    GameLogRow,
    LeaderCategory,
    LeaderRow,
    LeadersOut,
    PlayerSeasonStats,
    TeamSeasonRow,
)
from app.services.season import season_weeks
from app.services.serializers import player_summary, season_out, team_summary
from app.services.standings import compute_records
from app.sim.stats import PlayerLine

PLAYER_COLUMNS = list(PlayerLine.__dataclass_fields__)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    stat: str
    supporting: tuple[str, ...]


CATEGORIES: dict[str, Category] = {c.key: c for c in [
    Category("passing_yards", "Passing yards", "pass_yds",
             ("pass_cmp", "pass_att", "pass_td", "pass_int")),
    Category("passing_td", "Passing TD", "pass_td", ("pass_yds", "pass_int")),
    Category("rushing_yards", "Rushing yards", "rush_yds", ("rush_att", "rush_td", "rush_long")),
    Category("rushing_td", "Rushing TD", "rush_td", ("rush_yds", "rush_att")),
    Category("receiving_yards", "Receiving yards", "rec_yds",
             ("receptions", "targets", "rec_td", "rec_long")),
    Category("receptions", "Receptions", "receptions", ("targets", "rec_yds")),
    Category("receiving_td", "Receiving TD", "rec_td", ("receptions", "rec_yds")),
    Category("tackles", "Tackles", "tackles", ("sacks", "interceptions", "forced_fumbles")),
    Category("sacks", "Sacks", "sacks", ("tackles", "forced_fumbles")),
    Category("interceptions", "Interceptions", "interceptions",
             ("passes_defended", "int_return_yds")),
    Category("field_goals", "Field goals made", "fg_made", ("fg_att", "fg_long", "xp_made")),
]}

# Columns that are a maximum across games rather than a sum.
MAX_COLUMNS = {"rush_long", "rec_long", "fg_long"}


def _agg(column: str):
    col = getattr(PlayerGameStats, column)
    return (func.max(col) if column in MAX_COLUMNS else func.sum(col)).label(column)


def _teams_for(db: Session, season: Season, players: dict[int, Player]) -> dict[int, Team | None]:
    """Current team, or (free agents) the team of their most recent game this season."""
    result: dict[int, Team | None] = {pid: p.team for pid, p in players.items()}
    missing = [pid for pid, team in result.items() if team is None]
    if missing:
        rows = db.execute(
            select(PlayerGameStats.player_id, PlayerGameStats.team_id)
            .join(Game, Game.id == PlayerGameStats.game_id)
            .where(Game.season_id == season.id, PlayerGameStats.player_id.in_(missing))
            .order_by(Game.week)
        ).all()
        last = {pid: team_id for pid, team_id in rows}  # later weeks overwrite earlier
        for pid, team_id in last.items():
            result[pid] = db.get(Team, team_id)
    return result


def leaders(db: Session, season: Season, keys: list[str], limit: int) -> LeadersOut:
    categories = []
    for key in keys:
        category = CATEGORIES[key]
        columns = (category.stat, *category.supporting)
        stat_sum = func.sum(getattr(PlayerGameStats, category.stat))
        stmt = (
            select(PlayerGameStats.player_id,
                   func.count(func.distinct(PlayerGameStats.game_id)).label("games"),
                   *(_agg(c) for c in columns))
            .join(Game, Game.id == PlayerGameStats.game_id)
            .where(Game.season_id == season.id)
            .group_by(PlayerGameStats.player_id)
            .having(stat_sum > 0)
            .order_by(stat_sum.desc(), PlayerGameStats.player_id)
            .limit(limit)
        )
        rows = db.execute(stmt).mappings().all()
        players = {p.id: p for p in db.scalars(
            select(Player).where(Player.id.in_([r["player_id"] for r in rows]))
            .options(selectinload(Player.team).selectinload(Team.division)))}
        teams = _teams_for(db, season, players)
        categories.append(LeaderCategory(key=key, label=category.label, leaders=[
            LeaderRow(player_id=r["player_id"], name=players[r["player_id"]].full_name,
                      position=players[r["player_id"]].position,
                      team=team_summary(teams[r["player_id"]]) if teams[r["player_id"]] else None,
                      games=r["games"], value=int(r[category.stat]),
                      stats={c: int(r[c] or 0) for c in category.supporting})
            for r in rows
        ]))
    return LeadersOut(season=season_out(season, season_weeks(db, season.id)),
                      categories=categories)


def player_season(db: Session, player: Player, season: Season) -> PlayerSeasonStats:
    rows = db.execute(
        select(PlayerGameStats, Game).join(Game, Game.id == PlayerGameStats.game_id)
        .where(Game.season_id == season.id, PlayerGameStats.player_id == player.id)
        .order_by(Game.week)
    ).all()
    totals: dict[str, int] = {}
    log = []
    for stat, game in rows:
        line = {c: getattr(stat, c) for c in PLAYER_COLUMNS}
        for c, v in line.items():
            totals[c] = max(totals.get(c, 0), v) if c in MAX_COLUMNS else totals.get(c, 0) + v
        home = stat.team_id == game.home_team_id
        ours, theirs = ((game.home_score, game.away_score) if home
                        else (game.away_score, game.home_score))
        outcome = "W" if ours > theirs else "L" if ours < theirs else "T"
        log.append(GameLogRow(
            game_id=game.id, week=game.week, home=home,
            opponent=team_summary(game.away_team if home else game.home_team),
            result=f"{outcome} {ours}-{theirs}" + (" OT" if game.overtime else ""),
            stats={c: v for c, v in line.items() if v}))
    team = player.team or (_teams_for(db, season, {player.id: player})[player.id] if rows else None)
    return PlayerSeasonStats(
        player=player_summary(player), team=team_summary(team) if team else None,
        season=season_out(season, season_weeks(db, season.id)), games=len(rows),
        totals={c: v for c, v in totals.items() if v}, game_log=log)


def team_season(db: Session, season: Season) -> list[TeamSeasonRow]:
    teams = db.scalars(select(Team).where(Team.league_id == season.league_id)
                       .order_by(Team.id)).all()
    own = TeamGameStats
    opp = aliased(TeamGameStats)
    offense_cols = ("points", "total_yds", "pass_yds", "rush_yds", "first_downs", "turnovers",
                    "sacks_allowed", "penalties", "penalty_yds", "time_of_possession",
                    "third_down_att", "third_down_conv")
    stmt = (
        select(own.team_id, func.count(own.id).label("games"),
               *(func.sum(getattr(own, c)).label(c) for c in offense_cols),
               func.sum(opp.points).label("points_against"),
               func.sum(opp.total_yds).label("yds_allowed"),
               func.sum(opp.pass_yds).label("pass_yds_allowed"),
               func.sum(opp.rush_yds).label("rush_yds_allowed"),
               func.sum(opp.turnovers).label("takeaways"),
               func.sum(opp.sacks_allowed).label("sacks"))
        .join(opp, (opp.game_id == own.game_id) & (opp.team_id != own.team_id))
        .join(Game, Game.id == own.game_id)
        .where(Game.season_id == season.id)
        .group_by(own.team_id)
    )
    totals = {r["team_id"]: r for r in db.execute(stmt).mappings()}
    records = compute_records(db, season, [t.id for t in teams])
    rows = []
    for team in teams:
        t = totals.get(team.id, {})
        rec = records[team.id]

        def v(key: str, t=t) -> int:
            return int(t.get(key) or 0)

        rows.append(TeamSeasonRow(
            team=team_summary(team), games=v("games"), wins=rec.wins, losses=rec.losses,
            ties=rec.ties, points_for=v("points"), points_against=v("points_against"),
            **{c: v(c) for c in offense_cols if c != "points"},
            yds_allowed=v("yds_allowed"), pass_yds_allowed=v("pass_yds_allowed"),
            rush_yds_allowed=v("rush_yds_allowed"), takeaways=v("takeaways"), sacks=v("sacks")))
    return rows
