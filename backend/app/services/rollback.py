"""Rolling back the last week (or playoff round) (docs/design/head-to-head-and-commissioner.md
§4): its games, box scores, injuries, awards and notifications go; rosters stay as they are
now. Played again, a week that was played on its own plays the same (seeds come from the
games' ids); a week from a longer sim is played with the lineups as they are now (a long sim
builds lineups once, at its start).

Before each week or round is played, `snapshot` keeps what its games can't give back (the
season's phase and week, and every injury); `roll_back` puts it back. A league keeps only
its latest snapshot, so only the last week can be rolled back, and only once.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Award,
    CoachedGame,
    Game,
    LiveGame,
    Notification,
    Player,
    PlayerGameStats,
    PlayoffSeed,
    Season,
    StaffSeason,
    TeamGameStats,
    WeekSnapshot,
)
from app.services.errors import RosterError
from app.services.injuries import heal
from app.services.teams import current_season

# What playing a week tells members, which goes with it.
_WEEK_NOTIFICATIONS = ("advanced", "game_result", "live")


def snapshot(db: Session, season: Season, label: str, stage: str, games: list[Game],
             phase: str | None = None) -> None:
    """Keep what the coming week (or round) changes; `phase` is the season's before it
    started (week 1 moves the preseason on)."""
    db.execute(delete(WeekSnapshot).where(WeekSnapshot.league_id == season.league_id))
    rows = db.execute(select(Player.id, Player.injury, Player.injury_weeks,
                             Player.injury_status, Player.injury_count)
                      .where(Player.league_id == season.league_id,
                             Player.injury.is_not(None) | (Player.injury_count > 0))).all()
    db.add(WeekSnapshot(
        league_id=season.league_id, season_id=season.id, label=label, stage=stage,
        playoff_round=games[0].playoff_round if stage == "playoff" and games else None,
        phase=phase or season.phase, current_week=season.current_week,
        game_ids=[g.id for g in games],
        injuries={str(pid): [injury, weeks, status, count or 0]
                  for pid, injury, weeks, status, count in rows}))
    db.flush()


def latest(db: Session, season: Season | None) -> WeekSnapshot | None:
    """The week that can be rolled back (in the current season only)."""
    if season is None:
        return None
    return db.scalar(select(WeekSnapshot).where(WeekSnapshot.league_id == season.league_id,
                                                WeekSnapshot.season_id == season.id)
                     .order_by(WeekSnapshot.id.desc()).limit(1))


def roll_back(db: Session, league_id: int) -> str:
    """Undo the last week or playoff round. Returns its label."""
    season = current_season(db, league_id)
    shot = latest(db, season)
    if shot is None:
        raise RosterError("There's no week to roll back: only the last week (or playoff "
                          "round) of the current season, once.")
    game_ids = list(shot.game_ids)
    if db.scalar(select(CoachedGame.id).join(Game).where(
            Game.season_id == season.id, CoachedGame.status == "in_progress").limit(1)) or \
            db.scalar(select(LiveGame.id).join(Game).where(
                Game.season_id == season.id, LiveGame.status.in_(("in_progress", "proposed")))
                .limit(1)):
        raise RosterError("A game is being coached (or offered live): finish or abandon it "
                          "before rolling back.")

    # The week's games: unplayed again, without their box scores (and any coaching).
    for statement in (
        delete(PlayerGameStats).where(PlayerGameStats.game_id.in_(game_ids)),
        delete(TeamGameStats).where(TeamGameStats.game_id.in_(game_ids)),
        delete(CoachedGame).where(CoachedGame.game_id.in_(game_ids)),
        delete(LiveGame).where(LiveGame.game_id.in_(game_ids)),
    ):
        db.execute(statement)
    for game in db.scalars(select(Game).where(Game.id.in_(game_ids))):
        game.status, game.home_score, game.away_score = "scheduled", None, None
        game.overtime, game.seed, game.sim_version, game.play_log = False, None, None, None

    # What the week led to: the playoffs (seeds and the first round), the next round, the
    # champion and the season's awards.
    later = select(Game.id).where(Game.season_id == season.id, Game.stage == "playoff",
                                  Game.id.not_in(game_ids))
    if shot.stage == "playoff":
        later = later.where(Game.playoff_round > shot.playoff_round)
    else:
        db.execute(delete(PlayoffSeed).where(PlayoffSeed.season_id == season.id))
    later_ids = list(db.scalars(later))
    for statement in (
        delete(LiveGame).where(LiveGame.game_id.in_(later_ids)),
        delete(CoachedGame).where(CoachedGame.game_id.in_(later_ids)),
        delete(Game).where(Game.id.in_(later_ids)),
        delete(Award).where(Award.season_id == season.id),
        delete(StaffSeason).where(StaffSeason.season_id == season.id),
    ):
        db.execute(statement)
    from app.services.owners import unreview  # (owners build on the season services)

    unreview(db, season)  # (a rolled-back final: the owners' review goes too)
    season.champion_team_id = None
    season.phase, season.current_week = shot.phase, shot.current_week

    # Injuries as they were before the week.
    before = shot.injuries
    for player in db.scalars(select(Player).where(
            Player.league_id == league_id,
            Player.injury.is_not(None) | (Player.injury_count > 0)
            | Player.id.in_([int(pid) for pid in before]))):
        kept = before.get(str(player.id))
        if kept is None:
            heal(player)
            player.injury_count = 0
        else:
            player.injury, player.injury_weeks, player.injury_status, player.injury_count = kept

    # What members were told about the week.
    db.execute(delete(Notification).where(Notification.league_id == league_id,
                                          Notification.kind.in_(_WEEK_NOTIFICATIONS),
                                          Notification.created_at >= shot.created_at))
    label = shot.label
    db.delete(shot)
    db.flush()
    db.expire_all()
    return label
