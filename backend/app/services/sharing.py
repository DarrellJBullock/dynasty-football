"""Sharing and export (docs/design/leagues-with-friends.md §7).

- The read-only public link: a commissioner makes one (only its token's SHA-256 is kept,
  so it's shown once) and can revoke it; anyone with it sees the league without an
  account, through api/public.py. Making a new one revokes the old.
- The league export: the whole league as one JSON document, for members
  (docs/league-export.md describes the format).
"""

import hashlib
import secrets
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Award,
    Base,
    Conference,
    Contract,
    DeadMoney,
    DepthChartEntry,
    Division,
    DraftPick,
    Facility,
    Game,
    HallOfFameVote,
    League,
    Owner,
    OwnerSeason,
    Player,
    PlayerRatings,
    PlayoffSeed,
    RetiredNumber,
    Season,
    StaffDeadMoney,
    StaffMember,
    StaffSeason,
    Team,
    TeamGameStats,
    Trade,
)
from app.services.errors import RosterError

EXPORT_FORMAT = "dynasty-football/league"
EXPORT_VERSION = 1


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- the public link ----------

def create_link(db: Session, league: League) -> str:
    """A new public link's token (any earlier link stops working)."""
    token = secrets.token_urlsafe(24)
    league.share_token_hash = _hash(token)
    league.shared_at = datetime.now(UTC)
    db.flush()
    return token


def revoke_link(db: Session, league: League) -> None:
    league.share_token_hash = None
    league.shared_at = None
    db.flush()


def league_for(db: Session, token: str) -> League:
    """The league a public link shows (404 for a wrong or revoked one, alike)."""
    league = db.scalar(select(League).where(League.share_token_hash == _hash(token)))
    if league is None:
        raise RosterError("This link isn't shared any more.", 404)
    return league


# ---------- the export ----------

# What a league is made of, and what's left out: accounts, members, invites, notifications,
# offers' notes, game plans (private to their managers), background jobs, the League log
# (members' names), and the big logs
# (play-by-play, offseason logs), which can be replayed or rebuilt.
_SKIP = {
    League: {"user_id", "share_token_hash", "shared_at", "auto_advanced_at"},
    Season: {"offseason_log"},
    Game: {"play_log"},
}


def _value(value: object) -> object:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _row(row: Base) -> dict:
    skip = _SKIP.get(type(row), set())
    return {c.key: _value(getattr(row, c.key)) for c in row.__table__.columns
            if c.key not in skip}


def _rows(db: Session, model: type[Base], *where) -> list[dict]:
    """The rows as stored, read as plain rows (no ORM objects: a league has many)."""
    table = model.__table__
    skip = _SKIP.get(model, set())
    columns = [c for c in table.columns if c.key not in skip]
    stmt = select(*columns).where(*where).order_by(*table.primary_key.columns)
    return [{k: _value(v) for k, v in row.items()} for row in db.execute(stmt).mappings()]


def export_league(db: Session, league: League) -> dict:
    """The whole league, table by table (each row's columns as stored)."""
    team_ids = select(Team.id).where(Team.league_id == league.id)
    player_ids = select(Player.id).where(Player.league_id == league.id)
    season_ids = select(Season.id).where(Season.league_id == league.id)
    conference_ids = select(Conference.id).where(Conference.league_id == league.id)
    game_ids = select(Game.id).where(Game.season_id.in_(season_ids))
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "league": _row(league),
        "conferences": _rows(db, Conference, Conference.league_id == league.id),
        "divisions": _rows(db, Division, Division.conference_id.in_(conference_ids)),
        "teams": _rows(db, Team, Team.league_id == league.id),
        "players": _rows(db, Player, Player.league_id == league.id),
        "player_ratings": _rows(db, PlayerRatings, PlayerRatings.player_id.in_(player_ids)),
        "contracts": _rows(db, Contract, Contract.player_id.in_(player_ids)),
        "dead_money": _rows(db, DeadMoney, DeadMoney.team_id.in_(team_ids)),
        "depth_charts": _rows(db, DepthChartEntry, DepthChartEntry.team_id.in_(team_ids)),
        "seasons": _rows(db, Season, Season.league_id == league.id),
        "games": _rows(db, Game, Game.season_id.in_(season_ids)),
        "team_game_stats": _rows(db, TeamGameStats, TeamGameStats.game_id.in_(game_ids)),
        "playoff_seeds": _rows(db, PlayoffSeed, PlayoffSeed.season_id.in_(season_ids)),
        "awards": _rows(db, Award, Award.season_id.in_(season_ids)),
        "draft_picks": _rows(db, DraftPick, DraftPick.league_id == league.id),
        "trades": _rows(db, Trade, Trade.league_id == league.id),
        "hall_of_fame": _rows(db, HallOfFameVote, HallOfFameVote.league_id == league.id),
        "retired_numbers": _rows(db, RetiredNumber, RetiredNumber.team_id.in_(team_ids)),
        "staff": _rows(db, StaffMember, StaffMember.league_id == league.id),
        "staff_seasons": _rows(db, StaffSeason, StaffSeason.season_id.in_(season_ids)),
        "staff_dead_money": _rows(db, StaffDeadMoney, StaffDeadMoney.team_id.in_(team_ids)),
        "facilities": _rows(db, Facility, Facility.team_id.in_(team_ids)),
        "owners": _rows(db, Owner, Owner.league_id == league.id),
        "owner_seasons": _rows(db, OwnerSeason, OwnerSeason.season_id.in_(season_ids)),
    }


def export_filename(league: League) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in league.name.lower()).strip("-")
    return f"{safe or 'league'}-{datetime.now(UTC):%Y-%m-%d}.json"
