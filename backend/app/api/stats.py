from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.leagues import get_league
from app.api.players import get_player
from app.db import get_db
from app.models import League, Player, Season
from app.schemas import LeadersOut, PlayerSeasonStats, TeamSeasonRow
from app.services import league_stats
from app.services.teams import current_season

router = APIRouter(tags=["stats"])


def _season(db: Session, league_id: int) -> Season:
    season = current_season(db, league_id)
    if season is None:
        raise HTTPException(404, "league has no season")
    return season


@router.get("/leagues/{league_id}/leaders", response_model=LeadersOut)
def leaders(category: str | None = None, limit: int = Query(5, ge=1, le=50),
            league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Season leaders: every category (top `limit` each), or one category."""
    if category is not None and category not in league_stats.CATEGORIES:
        raise HTTPException(422, f"unknown category {category!r}; use one of: "
                                 + ", ".join(league_stats.CATEGORIES))
    keys = [category] if category else list(league_stats.CATEGORIES)
    return league_stats.leaders(db, _season(db, league.id), keys, limit)


@router.get("/leagues/{league_id}/team-stats", response_model=list[TeamSeasonRow])
def team_stats(league: League = Depends(get_league), db: Session = Depends(get_db)):
    """Season totals for every team: offense, defense, and record."""
    return league_stats.team_season(db, _season(db, league.id))


@router.get("/players/{player_id}/stats", response_model=PlayerSeasonStats)
def player_stats(player: Player = Depends(get_player), db: Session = Depends(get_db)):
    """A player's current-season totals and game log."""
    return league_stats.player_season(db, player, _season(db, player.league_id))
