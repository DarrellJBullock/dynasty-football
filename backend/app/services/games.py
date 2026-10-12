"""Read models for the schedule and game pages."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Game, Player, PlayerGameStats, Season, TeamGameStats
from app.schemas import GameDetail, GameInjury, PlayerGameLine, PlayOut, ScheduleWeek
from app.services.season import season_view, season_weeks
from app.services.serializers import game_out
from app.sim.playbook import defense_name, offense_name
from app.sim.stats import PlayerLine, TeamLine
from app.sim.text import spot_label

PLAYER_STATS = [f for f in PlayerLine.__dataclass_fields__]
TEAM_STATS = [f for f in TeamLine.__dataclass_fields__]


def schedule_week(db: Session, season: Season, week: int | None) -> ScheduleWeek:
    weeks = season_weeks(db, season.id)
    if week is None:
        week = min(season.current_week, weeks) if weeks else 1
    games = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == week)
                       .order_by(Game.id)).all()
    return ScheduleWeek(season=season_view(db, season), week=week,
                        games=[game_out(g) for g in games])


def line_score(play_log: list[dict]) -> dict[str, list[int]]:
    """Points per period from the score snapshot after each play."""
    periods = max((p["quarter"] for p in play_log), default=4)
    totals = {"home": [0] * max(4, periods), "away": [0] * max(4, periods)}
    previous = {"home": 0, "away": 0}
    for play in play_log:
        for side in ("home", "away"):
            gained = play["score"][side] - previous[side]
            if gained:
                totals[side][play["quarter"] - 1] += gained
        previous = play["score"]
    return totals


def play_out(play: dict, abbreviations: dict[str, str]) -> PlayOut:
    offense, side = play["offense"], play["side"]
    defense = abbreviations["away" if side == "home" else "home"]
    result = play["result"]
    scoring = bool(result.get("touchdown") or result.get("defensive_td")
                   or result.get("safety")
                   or (result.get("type") == "field_goal" and result.get("good")))
    spot = spot_label(play["ball_on"], offense, defense) if play["ball_on"] is not None else None
    return PlayOut(n=play["n"], quarter=play["quarter"], clock=play["clock"], offense=offense,
                   down=play["down"], distance=play["distance"], spot=spot,
                   type=result.get("type", ""), text=play["text"],
                   home_score=play["score"]["home"], away_score=play["score"]["away"],
                   scoring=scoring, play_name=offense_name(play.get("call")),
                   defense_name=defense_name(play.get("defense")))


def _injuries(db: Session, game: Game, log: list[dict]) -> list[GameInjury]:
    hurt = [(play, e) for play in log for e in play["events"] if e["t"] == "injury"]
    if not hurt:
        return []
    players = {p.id: p for p in db.scalars(
        select(Player).where(Player.id.in_({e["player"] for _, e in hurt})))}
    team_ids = {game.home_team.abbreviation: game.home_team_id,
                game.away_team.abbreviation: game.away_team_id}
    return [GameInjury(player_id=e["player"], team_id=team_ids[e["team"]],
                       name=players[e["player"]].full_name,
                       position=players[e["player"]].position, injury=e["injury"],
                       weeks=e["weeks"], quarter=play["quarter"], clock=play["clock"])
            for play, e in hurt if e["player"] in players]


def game_detail(db: Session, game: Game) -> GameDetail:
    sides = {game.home_team_id: "home", game.away_team_id: "away"}
    team_stats = {sides[row.team_id]: {f: getattr(row, f) for f in TEAM_STATS}
                  for row in db.scalars(select(TeamGameStats)
                                        .where(TeamGameStats.game_id == game.id))}
    rows = db.scalars(select(PlayerGameStats).where(PlayerGameStats.game_id == game.id)
                      .options(selectinload(PlayerGameStats.player))).all()
    players = [
        PlayerGameLine(player_id=row.player_id, team_id=row.team_id,
                       name=row.player.full_name, position=row.player.position,
                       stats={f: getattr(row, f) for f in PLAYER_STATS if getattr(row, f)})
        for row in rows
    ]
    log = game.play_log or []
    abbreviations = {"home": game.home_team.abbreviation, "away": game.away_team.abbreviation}
    plays = [play_out(p, abbreviations) for p in log]
    return GameDetail(
        injuries=_injuries(db, game, log),
        game=game_out(game),
        season_year=game.season.year,
        line_score=line_score(log) if log else {"home": [], "away": []},
        team_stats=team_stats,
        players=players,
        scoring_plays=[p for p in plays if p.scoring],
        plays=plays,
        log_compacted=game.log_compacted,
    )
