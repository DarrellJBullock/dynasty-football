"""Write player rows as CSV, XLSX, or JSON in the import format.

Used by import templates and roster exports, so anything written here reads back
through readers.py + rows.py unchanged.
"""

import csv
import io
import json
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from app.domain.ratings import ATTRIBUTES
from app.roster_import.readers import FileFormat

BIO_COLUMNS = [
    "first_name", "last_name", "position", "jersey_number", "age", "height_in", "weight_lb",
    "college", "years_pro", "potential", "development_trait", "injury_status", "salary",
    "contract_years",
]
COLUMNS = BIO_COLUMNS + list(ATTRIBUTES)

MEDIA_TYPES = {
    FileFormat.CSV: "text/csv",
    FileFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileFormat.JSON: "application/json",
}

Row = dict[str, Any]


def write_rows(rows: list[Row], fmt: FileFormat, *, sheet_title: str = "Roster",
               meta: dict[str, Any] | None = None) -> bytes:
    """Serialize rows (keyed by COLUMNS; missing or None values are left blank).

    `meta` is extra top-level JSON data placed alongside "players" (ignored for CSV/XLSX).
    """
    table = [[_cell(row.get(column)) for column in COLUMNS] for row in rows]
    if fmt is FileFormat.CSV:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        writer.writerows(table)
        return buffer.getvalue().encode()
    if fmt is FileFormat.XLSX:
        return _xlsx(table, sheet_title)
    players = [{k: row[k] for k in COLUMNS if row.get(k) not in (None, "")} for row in rows]
    return json.dumps({**(meta or {}), "players": players}, indent=2).encode()


def _cell(value: Any) -> Any:
    return "" if value is None else value


def _xlsx(table: list[list[Any]], title: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]  # Excel's sheet-name limit
    sheet.append(COLUMNS)
    for row in table:
        sheet.append([None if value == "" else value for value in row])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for index, column in enumerate(COLUMNS, start=1):
        width = max(len(column), *(len(str(row[index - 1])) for row in table)) if table \
            else len(column)
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = min(width + 2, 28)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
