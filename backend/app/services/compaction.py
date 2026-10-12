"""Play-log compaction: leagues that sim ahead fill the database fast (about 9 MB of play
logs a season). Seasons older than last season keep full play-by-play only for the
franchise's games and the playoffs; other games keep just the plays the box score page
is built from: every play that changed the score (the line score and scoring summary)
or hurt someone (the injury list), and the last play (the final period). Box scores,
stats, records and careers come from `player_game_stats` / `team_game_stats` and don't
change. Design: docs/design/dynasty-mode.md §3."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, undefer

from app.models import Franchise, Game, Season


def compact_log(log: list[dict]) -> list[dict]:
    """The plays a compacted game keeps."""
    kept = []
    previous = {"home": 0, "away": 0}
    for i, play in enumerate(log):
        scored = play["score"] != previous
        hurt = any(e["t"] == "injury" for e in play["events"])
        if scored or hurt or i == len(log) - 1:
            kept.append(play)
        previous = play["score"]
    return kept


def compact_old_seasons(db: Session, league_id: int, current_year: int) -> int:
    """Compact the eligible games of seasons before last season. Returns how many."""
    franchise_team = db.scalar(select(Franchise.team_id).where(Franchise.league_id == league_id))
    games = db.scalars(
        select(Game).join(Season).options(undefer(Game.play_log))
        .where(Season.league_id == league_id, Season.year < current_year - 1,
               Game.status == "final", Game.stage == "regular",
               Game.log_compacted.is_(False), Game.play_log.is_not(None),
               ~or_(Game.home_team_id == franchise_team, Game.away_team_id == franchise_team)))
    count = 0
    for game in games:
        game.play_log = compact_log(game.play_log)
        game.log_compacted = True
        count += 1
    db.flush()
    return count
