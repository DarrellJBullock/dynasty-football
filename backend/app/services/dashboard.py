"""Assembles the franchise dashboard in a single response."""

from statistics import mean

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.positions import ROSTER_MAX, Position, PositionGroup, group_of
from app.models import Franchise, Game, Player
from app.schemas import (
    Alert,
    Dashboard,
    FranchiseOut,
    PositionGroupSummary,
    Record,
)
from app.services.serializers import (
    game_out,
    league_out,
    player_summary,
    season_out,
    team_summary,
)
from app.services.standings import league_standings
from app.services.teams import current_season, load_overrides, load_roster, team_detail, team_lineup

UPCOMING_GAMES = 5
TOP_PLAYERS = 6


def current_franchise(db: Session) -> Franchise | None:
    """Single-save for now: the earliest franchise is the active one."""
    return db.scalars(select(Franchise).order_by(Franchise.id)).first()


def franchise_out(db: Session, franchise: Franchise) -> FranchiseOut:
    season = current_season(db, franchise.league_id)
    return FranchiseOut(id=franchise.id, name=franchise.name,
                        league=league_out(franchise.league),
                        team=team_summary(franchise.team), season=season_out(season))


def _position_groups(roster: list[Player],
                     lineup: dict[Position, list[Player]]) -> list[PositionGroupSummary]:
    starters = {p.id for players in lineup.values() for p in players}
    summaries = []
    for group in PositionGroup:
        members = [p for p in roster if group_of(p.position) == group]
        starting = [p.overall for p in members if p.id in starters]
        summaries.append(PositionGroupSummary(
            group=group,
            count=len(members),
            average_overall=round(mean(p.overall for p in members)) if members else 0,
            starter_overall=round(mean(starting)) if starting else 0,
        ))
    return summaries


def _alerts(roster: list[Player], cap_space: int, expiring: int,
            groups: list[PositionGroupSummary]) -> list[Alert]:
    alerts: list[Alert] = []
    if cap_space < 0:
        alerts.append(Alert(level="critical", message="Payroll is over the salary cap."))
    elif cap_space < 5_000_000:
        alerts.append(Alert(level="warning", message="Less than $5M in cap space remaining."))
    open_spots = ROSTER_MAX - len(roster)
    if open_spots > 0:
        alerts.append(Alert(level="info",
                            message=f"{open_spots} open roster spot(s) — check free agency."))
    injured = [p for p in roster if p.injury_status != "healthy"]
    if injured:
        alerts.append(Alert(level="warning",
                            message=f"{len(injured)} player(s) on the injury report."))
    if expiring:
        alerts.append(Alert(level="info",
                            message=f"{expiring} contract(s) expire after this season."))
    weakest = min((g for g in groups if g.starter_overall), key=lambda g: g.starter_overall,
                  default=None)
    if weakest is not None:
        alerts.append(Alert(level="info",
                            message=f"Weakest starting unit: {weakest.group.value} "
                                    f"({weakest.starter_overall} OVR)."))
    return alerts


def build_dashboard(db: Session, franchise: Franchise) -> Dashboard:
    team = franchise.team
    league = franchise.league
    season = current_season(db, league.id)
    roster = load_roster(db, team.id)
    overrides = load_overrides(db, [team.id])[team.id]
    detail = team_detail(team, roster, overrides)

    standings = league_standings(db, league, season)
    division = next(d for d in standings if d.division == team.division.name)
    own_row = next(r for r in division.rows if r.team.id == team.id)

    upcoming = db.scalars(
        select(Game)
        .where(Game.season_id == season.id, Game.status == "scheduled",
               or_(Game.home_team_id == team.id, Game.away_team_id == team.id))
        .order_by(Game.week)
        .limit(UPCOMING_GAMES)
    )
    expiring = sum(1 for p in roster
                   if (c := p.active_contract) is not None and c.end_year <= season.year)
    groups = _position_groups(roster, team_lineup(roster, overrides))

    return Dashboard(
        franchise=franchise_out(db, franchise),
        team=detail,
        record=Record(wins=own_row.wins, losses=own_row.losses, ties=own_row.ties),
        division_standings=division,
        upcoming_games=[game_out(g) for g in upcoming],
        top_players=[player_summary(p) for p in roster[:TOP_PLAYERS]],
        position_groups=groups,
        expiring_contracts=expiring,
        alerts=_alerts(roster, detail.cap_space, expiring, groups),
    )
