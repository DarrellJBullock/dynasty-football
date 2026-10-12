from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.access import current_user
from app.api.errors import roster_errors
from app.db import get_db
from app.domain.positions import Position
from app.models import League, Player, Team, User
from app.schemas import (
    DivisionStandings,
    FranchiseOut,
    LeagueCreate,
    LeagueOut,
    PlayerSummary,
    TeamDetail,
)
from app.seed.generator import league_template
from app.services import leagues as league_service
from app.services.dashboard import franchise_out
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
def list_leagues(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [league_out(league) for league in db.scalars(
        select(League).where(League.user_id == user.id).order_by(League.id))]


@router.get("/template", response_model=LeagueCreate)
def template(conferences: int = Query(2, ge=1, le=4), divisions: int = Query(4, ge=1, le=4),
             teams_per_division: int = Query(4, ge=1, le=8)):
    """An editable custom-league spec filled with fictional teams."""
    try:
        return league_template(conferences, divisions, teams_per_division)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", response_model=FranchiseOut, status_code=201)
def create_league(spec: LeagueCreate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Create a league and the user's franchise in it; the franchise becomes active."""
    with roster_errors(db):
        franchise = league_service.create_league(db, spec, user)
    return franchise_out(db, franchise)


@router.delete("/{league_id}", status_code=204)
def delete_league(league: League = Depends(get_league), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    with roster_errors(db):
        league_service.delete_league(db, league, user)


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
        .where(Player.league_id == league.id, Player.team_id.is_(None),
               Player.retired_year.is_(None), Player.is_prospect.is_(False))
        .options(selectinload(Player.ratings), selectinload(Player.contracts))
        .order_by(Player.overall.desc(), Player.id)
    )
    if position is not None:
        stmt = stmt.where(Player.position == position.value)
    return [player_summary(p) for p in db.scalars(stmt)]
