from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.domain.positions import Position
from app.models import League, Player, Team
from app.schemas import DivisionStandings, LeagueOut, PlayerSummary, TeamDetail
from app.services.serializers import league_out, player_summary
from app.services.standings import league_standings
from app.services.teams import current_season, load_overrides, team_detail

router = APIRouter(prefix="/leagues", tags=["leagues"])


def get_league(league_id: int, db: Session = Depends(get_db)) -> League:
    league = db.get(League, league_id)
    if league is None:
        raise HTTPException(404, "league not found")
    return league


@router.get("", response_model=list[LeagueOut])
def list_leagues(db: Session = Depends(get_db)):
    return [league_out(league) for league in db.scalars(select(League).order_by(League.id))]


@router.get("/{league_id}", response_model=LeagueOut)
def read_league(league: League = Depends(get_league)):
    return league_out(league)


@router.get("/{league_id}/teams", response_model=list[TeamDetail])
def list_teams(league: League = Depends(get_league), db: Session = Depends(get_db)):
    players = db.scalars(
        select(Player)
        .where(Player.league_id == league.id, Player.team_id.is_not(None))
        .options(selectinload(Player.contracts))
    ).all()
    by_team: dict[int, list[Player]] = {}
    for player in players:
        by_team.setdefault(player.team_id, []).append(player)
    teams = db.scalars(select(Team).where(Team.league_id == league.id).order_by(Team.id)).all()
    overrides = load_overrides(db, [team.id for team in teams])
    return [team_detail(team, by_team.get(team.id, []), overrides[team.id]) for team in teams]


@router.get("/{league_id}/standings", response_model=list[DivisionStandings])
def standings(league: League = Depends(get_league), db: Session = Depends(get_db)):
    season = current_season(db, league.id)
    if season is None:
        raise HTTPException(404, "league has no season")
    return league_standings(db, league, season)


@router.get("/{league_id}/free-agents", response_model=list[PlayerSummary])
def free_agents(position: Position | None = None, league: League = Depends(get_league),
                db: Session = Depends(get_db)):
    stmt = (
        select(Player)
        .where(Player.league_id == league.id, Player.team_id.is_(None))
        .options(selectinload(Player.ratings), selectinload(Player.contracts))
        .order_by(Player.overall.desc(), Player.id)
    )
    if position is not None:
        stmt = stmt.where(Player.position == position.value)
    return [player_summary(p) for p in db.scalars(stmt)]
