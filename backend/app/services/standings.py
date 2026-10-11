"""Standings derived from final game results."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Game, League, Season, Team
from app.schemas import DivisionStandings, StandingRow
from app.services.serializers import team_summary


@dataclass
class TeamRecord:
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: int = 0
    points_against: int = 0

    @property
    def win_pct(self) -> float:
        games = self.wins + self.losses + self.ties
        return round((self.wins + 0.5 * self.ties) / games, 3) if games else 0.0


def compute_records(db: Session, season: Season, team_ids: list[int]) -> dict[int, TeamRecord]:
    records = {team_id: TeamRecord() for team_id in team_ids}
    finals = db.scalars(
        select(Game).where(Game.season_id == season.id, Game.status == "final",
                           Game.stage == "regular")
    )
    for game in finals:
        home, away = records.get(game.home_team_id), records.get(game.away_team_id)
        hs, as_ = game.home_score or 0, game.away_score or 0
        for rec, pf, pa in ((home, hs, as_), (away, as_, hs)):
            if rec is None:
                continue
            rec.points_for += pf
            rec.points_against += pa
            if pf > pa:
                rec.wins += 1
            elif pf < pa:
                rec.losses += 1
            else:
                rec.ties += 1
    return records


def _row(team: Team, rec: TeamRecord) -> StandingRow:
    return StandingRow(team=team_summary(team), wins=rec.wins, losses=rec.losses,
                       ties=rec.ties, points_for=rec.points_for,
                       points_against=rec.points_against, win_pct=rec.win_pct)


def league_standings(db: Session, league: League, season: Season) -> list[DivisionStandings]:
    records = compute_records(db, season, [t.id for t in league.teams])
    result = []
    for conference in league.conferences:
        for division in conference.divisions:
            rows = [_row(team, records[team.id]) for team in division.teams]
            rows.sort(key=lambda r: (-r.win_pct, -(r.points_for - r.points_against),
                                     r.team.full_name))
            result.append(DivisionStandings(division=division.name,
                                            conference=conference.name, rows=rows))
    return result
