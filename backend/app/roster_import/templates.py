"""Downloadable import templates (CSV, XLSX, JSON) with example fictional players."""

import csv
import io
import json

from openpyxl import Workbook

from app.domain.positions import Position
from app.domain.ratings import ATTRIBUTES, POSITION_WEIGHTS
from app.roster_import.readers import FileFormat

BIO_COLUMNS = [
    "first_name", "last_name", "position", "jersey_number", "age", "height_in", "weight_lb",
    "college", "potential", "development_trait", "injury_status", "salary", "contract_years",
]
COLUMNS = BIO_COLUMNS + list(ATTRIBUTES)


def _example(position: Position, key_rating: int, **bio) -> dict:
    weights = POSITION_WEIGHTS[position]
    ratings = {name: key_rating if name in weights else 50 for name in ATTRIBUTES}
    return {"position": position.value, **bio, **ratings}


EXAMPLES = [
    _example(Position.QB, 84, first_name="Marcus", last_name="Hollister", jersey_number=7,
             age=26, height_in=75, weight_lb=220, college="Lakeshore State", potential=90,
             development_trait="star", injury_status="healthy", salary=28_000_000,
             contract_years=4),
    _example(Position.CB, 76, first_name="Devin", last_name="Okafor", jersey_number=24,
             age=23, height_in=71, weight_lb=190, college="Red River", potential=85,
             development_trait="normal", injury_status="healthy", salary="",
             contract_years=2),
]

MEDIA_TYPES = {
    FileFormat.CSV: "text/csv",
    FileFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileFormat.JSON: "application/json",
}


def build_template(fmt: FileFormat) -> bytes:
    rows = [[example.get(column, "") for column in COLUMNS] for example in EXAMPLES]
    if fmt is FileFormat.CSV:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
        return buffer.getvalue().encode()
    if fmt is FileFormat.XLSX:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Roster"
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append([None if value == "" else value for value in row])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
    players = [{k: v for k, v in example.items() if v != ""} for example in EXAMPLES]
    return json.dumps({"players": players}, indent=2).encode()
