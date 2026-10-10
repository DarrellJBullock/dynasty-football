"""Roster export in the import format, so an exported file re-imports unchanged."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.positions import Position
from app.models import Player, Team
from app.roster_import.readers import FileFormat
from app.roster_import.writers import Row, write_rows
from app.services.teams import current_season, load_roster

POSITION_ORDER = {position.value: index for index, position in enumerate(Position)}


def player_row(player: Player, season_year: int) -> Row:
    contract = player.active_contract
    return {
        "first_name": player.first_name,
        "last_name": player.last_name,
        "position": player.position,
        "jersey_number": player.jersey_number,
        "age": player.age,
        "height_in": player.height_in,
        "weight_lb": player.weight_lb,
        "college": player.college,
        "years_pro": player.years_pro,
        "potential": player.potential,
        "development_trait": player.development_trait,
        "injury_status": player.injury_status,
        "salary": contract.salary if contract else None,
        # Remaining seasons, counting this one, so a re-import keeps the same end year.
        "contract_years": max(1, contract.end_year - season_year + 1) if contract else None,
        **player.ratings.as_dict(),
    }


def export_roster(db: Session, team: Team, fmt: FileFormat) -> tuple[bytes, str]:
    """Returns (file bytes, download filename)."""
    season = current_season(db, team.league_id)
    year = season.year if season else datetime.now(UTC).year
    roster = sorted(load_roster(db, team.id),
                    key=lambda p: (POSITION_ORDER[p.position], -p.overall, p.last_name))
    meta = {
        "team": team.full_name,
        "abbreviation": team.abbreviation,
        "season": year,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    content = write_rows([player_row(p, year) for p in roster], fmt,
                         sheet_title=f"{team.abbreviation} {year}", meta=meta)
    return content, f"{team.abbreviation}-roster-{year}.{fmt.value}"
