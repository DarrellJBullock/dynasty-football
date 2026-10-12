"""The Dynasty report (after a sim ahead, or any span of seasons): each season's result
and awards, and the franchise's offseason after it. Design: docs/design/dynasty-mode.md §3."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, undefer

from app.models import Franchise, League, Player, Season, Team
from app.schemas import DynastyReport, DynastySeason
from app.services.errors import RosterError
from app.services.history import season_histories
from app.services.offseason import recap

MAX_SEASONS = 10


def report(db: Session, league: League, from_year: int, to_year: int) -> DynastyReport:
    if to_year < from_year:
        raise RosterError("The report's last season comes before its first.", 422)
    if to_year - from_year + 1 > MAX_SEASONS:
        raise RosterError(f"A report covers up to {MAX_SEASONS} seasons.", 422)
    team_id = db.scalar(select(Franchise.team_id).where(Franchise.league_id == league.id))
    # Every season names teams (champions, award winners, signings): load them, with
    # their divisions, once rather than one by one. (Held here: the session only keeps
    # objects something still refers to.)
    teams = db.scalars(select(Team).where(Team.league_id == league.id)
                       .options(selectinload(Team.division))).all()
    after = {s.year: s for s in db.scalars(select(Season).where(
        Season.league_id == league.id, Season.year.between(from_year + 1, to_year + 1))
        .options(undefer(Season.offseason_log)))}
    histories = season_histories(db, league, range(from_year, to_year + 1))
    roster = list(db.scalars(select(Player).where(Player.team_id == team_id).options(
        selectinload(Player.ratings), selectinload(Player.contracts)))) if team_id else []
    report = DynastyReport(from_year=from_year, to_year=to_year, seasons=[
        DynastySeason(season=history,
                      offseason=recap(db, after[history.year + 1], team_id, roster,
                                      {t.id: t for t in teams})
                      if history.year + 1 in after and team_id else None)
        for history in reversed(histories)])
    del teams
    return report
