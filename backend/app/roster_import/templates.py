"""Downloadable import templates (CSV, XLSX, JSON) with example fictional players."""

from app.domain.positions import Position
from app.domain.ratings import ATTRIBUTES, POSITION_WEIGHTS
from app.roster_import.readers import FileFormat
from app.roster_import.writers import write_rows


def _example(position: Position, key_rating: int, **bio) -> dict:
    weights = POSITION_WEIGHTS[position]
    ratings = {name: key_rating if name in weights else 50 for name in ATTRIBUTES}
    return {"position": position.value, **bio, **ratings}


EXAMPLES = [
    _example(Position.QB, 84, first_name="Marcus", last_name="Hollister", jersey_number=7,
             age=26, height_in=75, weight_lb=220, college="Lakeshore State", years_pro=4,
             potential=90, development_trait="star", injury_status="healthy", salary=28_000_000,
             contract_years=4),
    _example(Position.CB, 76, first_name="Devin", last_name="Okafor", jersey_number=24,
             age=23, height_in=71, weight_lb=190, college="Red River", years_pro=1,
             potential=85, development_trait="normal", injury_status="healthy", salary=None,
             contract_years=2),
]


def build_template(fmt: FileFormat) -> bytes:
    return write_rows(EXAMPLES, fmt)
