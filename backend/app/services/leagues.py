"""Custom leagues, team identities, and switching between franchises."""

import random
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Award,
    Conference,
    Contract,
    DeadMoney,
    DepthChartEntry,
    Division,
    DraftPick,
    Franchise,
    FreeAgentOffer,
    Game,
    League,
    Player,
    PlayerGameStats,
    PlayerRatings,
    PlayoffSeed,
    Season,
    Team,
    TeamGameStats,
    Trade,
)
from app.schemas import FranchiseListItem, LeagueCreate, TeamUpdate
from app.seed.generator import build_league
from app.services.dashboard import current_franchise, franchise_out
from app.services.errors import RosterError


def create_league(db: Session, spec: LeagueCreate) -> Franchise:
    seed = spec.seed if spec.seed is not None else random.SystemRandom().randrange(2**31)
    return build_league(db, spec, seed)


def list_franchises(db: Session) -> list[FranchiseListItem]:
    active = current_franchise(db)
    team_counts = dict(db.execute(select(Team.league_id, func.count(Team.id))
                                  .group_by(Team.league_id)).all())
    franchises = db.scalars(select(Franchise).order_by(Franchise.activated_at.desc(),
                                                       Franchise.id.desc()))
    return [
        FranchiseListItem(**franchise_out(db, f).model_dump(),
                          is_active=active is not None and f.id == active.id,
                          team_count=team_counts.get(f.league_id, 0))
        for f in franchises
    ]


def activate_franchise(db: Session, franchise: Franchise) -> Franchise:
    franchise.activated_at = datetime.now(UTC)
    db.flush()
    return franchise


def update_team(db: Session, team: Team, payload: TeamUpdate) -> Team:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    abbreviation = changes.get("abbreviation")
    if abbreviation and abbreviation != team.abbreviation:
        clash = db.scalar(select(Team).where(Team.league_id == team.league_id,
                                             Team.abbreviation == abbreviation,
                                             Team.id != team.id))
        if clash is not None:
            raise RosterError(f"{abbreviation} is already used by the {clash.full_name}")
    for field, value in changes.items():
        setattr(team, field, value)
    db.flush()
    return team


def delete_league(db: Session, league: League) -> None:
    """Delete a league and everything in it. The active franchise's league is protected."""
    active = current_franchise(db)
    if active is not None and active.league_id == league.id:
        raise RosterError("This is your active franchise's league. Switch to another "
                          "franchise before deleting it.")
    # Explicit child-first deletes, so this works without database-level cascades.
    team_ids = select(Team.id).where(Team.league_id == league.id)
    player_ids = select(Player.id).where(Player.league_id == league.id)
    season_ids = select(Season.id).where(Season.league_id == league.id)
    conference_ids = select(Conference.id).where(Conference.league_id == league.id)
    for stmt in (
        delete(DepthChartEntry).where(DepthChartEntry.team_id.in_(team_ids)),
        delete(Contract).where(Contract.player_id.in_(player_ids)),
        delete(DeadMoney).where(DeadMoney.team_id.in_(team_ids)),
        delete(PlayerRatings).where(PlayerRatings.player_id.in_(player_ids)),
        delete(PlayoffSeed).where(PlayoffSeed.season_id.in_(season_ids)),
        delete(Award).where(Award.season_id.in_(season_ids)),
        delete(FreeAgentOffer).where(FreeAgentOffer.season_id.in_(season_ids)),
        delete(DraftPick).where(DraftPick.league_id == league.id),
        delete(Trade).where(Trade.league_id == league.id),
        delete(PlayerGameStats).where(PlayerGameStats.player_id.in_(player_ids)),
        delete(TeamGameStats).where(TeamGameStats.team_id.in_(team_ids)),
        delete(Game).where(Game.season_id.in_(season_ids)),
        delete(Franchise).where(Franchise.league_id == league.id),
        delete(Player).where(Player.league_id == league.id),
        delete(Season).where(Season.league_id == league.id),
        delete(Team).where(Team.league_id == league.id),
        delete(Division).where(Division.conference_id.in_(conference_ids)),
        delete(Conference).where(Conference.league_id == league.id),
        delete(League).where(League.id == league.id),
    ):
        db.execute(stmt)
    db.expunge(league)
    db.flush()
