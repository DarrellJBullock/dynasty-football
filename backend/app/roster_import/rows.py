"""Turn raw rows into validated player data with per-row errors and warnings.

Pure functions: no database. Roster-level checks (capacity, jersey clashes with the
existing roster, payroll) happen in app/services/roster_import.py.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain.positions import Position
from app.domain.ratings import ATTRIBUTES, POSITION_WEIGHTS, RATING_MAX, calculate_overall
from app.roster_import.readers import RawRow

DEFAULT_RATING = 50
DEVELOPMENT_TRAITS = ("normal", "impact", "star", "elite")
INJURY_STATUSES = ("healthy", "questionable", "out", "injured_reserve")

# Common position labels from other games/spreadsheets -> our positions.
POSITION_ALIASES: dict[str, Position] = {
    "HB": Position.RB, "TB": Position.RB,
    "T": Position.OT, "LT": Position.OT, "RT": Position.OT,
    "G": Position.OG, "LG": Position.OG, "RG": Position.OG, "OC": Position.C,
    "EDGE": Position.DE, "LE": Position.DE, "RE": Position.DE,
    "NT": Position.DT, "DI": Position.DT,
    "LB": Position.MLB, "ILB": Position.MLB, "MIKE": Position.MLB,
    "LOLB": Position.OLB, "ROLB": Position.OLB,
    "S": Position.SS, "PK": Position.K,
}

# Short rating labels shown in the roster table (frontend/src/lib/attributes.ts).
ATTRIBUTE_ABBREVIATIONS: dict[str, str] = {
    "spd": "speed", "acc": "acceleration", "str": "strength", "agi": "agility",
    "sta": "stamina", "tgh": "toughness", "awr": "awareness", "thp": "throw_power",
    "tha": "throw_accuracy", "car": "carrying", "bcv": "ball_carrier_vision",
    "elu": "elusiveness", "cth": "catching", "rte": "route_running", "rbk": "run_blocking",
    "pbk": "pass_blocking", "tak": "tackling", "prs": "pass_rush", "bsh": "block_shedding",
    "mcv": "man_coverage", "zcv": "zone_coverage", "prc": "play_recognition",
    "kpw": "kick_power", "kac": "kick_accuracy",
}

COLUMN_ALIASES: dict[str, str] = {
    **{name: name for name in ATTRIBUTES},
    **ATTRIBUTE_ABBREVIATIONS,
    "first_name": "first_name", "first": "first_name", "firstname": "first_name",
    "fname": "first_name", "given_name": "first_name",
    "last_name": "last_name", "last": "last_name", "lastname": "last_name",
    "lname": "last_name", "surname": "last_name",
    "name": "name", "full_name": "name", "player": "name", "player_name": "name",
    "position": "position", "pos": "position",
    "jersey_number": "jersey_number", "jersey": "jersey_number", "number": "jersey_number",
    "no": "jersey_number", "num": "jersey_number", "#": "jersey_number",
    "age": "age",
    "height_in": "height_in", "height": "height_in", "ht": "height_in",
    "height_inches": "height_in",
    "weight_lb": "weight_lb", "weight": "weight_lb", "wt": "weight_lb",
    "weight_lbs": "weight_lb",
    "college": "college", "school": "college",
    "years_pro": "years_pro", "experience": "years_pro", "exp": "years_pro",
    "potential": "potential", "pot": "potential",
    "development_trait": "development_trait", "dev_trait": "development_trait",
    "dev": "development_trait", "development": "development_trait",
    "injury_status": "injury_status", "injury": "injury_status", "status": "injury_status",
    "overall": "overall", "ovr": "overall",
    "salary": "salary", "contract_years": "contract_years", "years": "contract_years",
}

# Columns the API itself emits that carry no importable data.
IGNORED_COLUMNS = {"id", "team_id", "team", "position_group", "key_ratings", "contract",
                   "ratings", "league_id"}

Level = Literal["error", "warning"]


@dataclass
class RowMessage:
    level: Level
    message: str


@dataclass
class ParsedRow:
    row_number: int  # 1-based data row (header excluded)
    first_name: str = ""
    last_name: str = ""
    position: Position | None = None
    jersey_number: int | None = None
    age: int = 22
    height_in: int = 74
    weight_lb: int = 220
    college: str = "Undrafted"
    years_pro: int = 0
    potential: int | None = None
    development_trait: str = "normal"
    injury_status: str = "healthy"
    salary: int | None = None
    contract_years: int = 1
    ratings: dict[str, int] = field(default_factory=dict)
    overall: int | None = None
    messages: list[RowMessage] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(m.level == "error" for m in self.messages)

    def error(self, message: str) -> None:
        self.messages.append(RowMessage("error", message))

    def warn(self, message: str) -> None:
        self.messages.append(RowMessage("warning", message))


@dataclass
class ParsedFile:
    rows: list[ParsedRow]
    warnings: list[str]


def normalize_header(name: Any) -> str:
    key = str(name).strip().lower()
    if key == "#":
        return key
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")


def parse_rows(raw_rows: list[RawRow]) -> ParsedFile:
    columns: dict[str, str] = {}  # original header -> canonical field
    unknown: list[str] = []
    for row in raw_rows:
        for header in row:
            if header in columns or header in unknown:
                continue
            key = normalize_header(header)
            if key in COLUMN_ALIASES:
                columns[header] = COLUMN_ALIASES[key]
            elif key not in IGNORED_COLUMNS:
                unknown.append(header)

    warnings = []
    if unknown:
        warnings.append(f"Ignored unrecognized column(s): {', '.join(map(str, unknown))}.")
    if not any(target in ("first_name", "name") for target in columns.values()):
        warnings.append("No name columns found (expected first_name/last_name or name).")
    if "position" not in columns.values():
        warnings.append("No position column found.")

    parsed = []
    for index, raw in enumerate(raw_rows, start=1):
        values: dict[str, Any] = {}
        for header, value in raw.items():
            target = columns.get(header)
            if target is not None and _present(value) and target not in values:
                values[target] = value
        parsed.append(parse_row(index, values))
    return ParsedFile(rows=parsed, warnings=warnings)


def parse_row(row_number: int, values: dict[str, Any]) -> ParsedRow:
    row = ParsedRow(row_number=row_number)
    _names(row, values)
    _position(row, values)

    row.jersey_number = _int_field(row, values, "jersey_number", "Jersey #", 0, 99)
    row.age = _int_field(row, values, "age", "Age", 18, 50, default=row.age)
    row.height_in = _height(row, values.get("height_in"))
    row.weight_lb = _int_field(row, values, "weight_lb", "Weight", 140, 400, default=row.weight_lb)
    row.years_pro = _int_field(row, values, "years_pro", "Years pro", 0, 30, default=0)
    row.contract_years = _int_field(row, values, "contract_years", "Contract years", 1, 7,
                                    default=1)
    row.salary = _int_field(row, values, "salary", "Salary", 0, 1_000_000_000)
    if "college" in values:
        row.college = str(values["college"]).strip()[:60] or row.college
    row.development_trait = _choice(row, values, "development_trait", "Development trait",
                                    DEVELOPMENT_TRAITS, "normal")
    row.injury_status = _choice(row, values, "injury_status", "Injury status",
                                INJURY_STATUSES, "healthy")
    _ratings(row, values)
    return row


# ---------- field helpers ----------

def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(text)
    except ValueError:
        return None


def _int_field(row: ParsedRow, values: dict, key: str, label: str, low: int, high: int,
               default: int | None = None) -> Any:
    if key not in values:
        return default
    number = _to_number(values[key])
    if number is None:
        row.error(f"{label} must be a number (got {values[key]!r}).")
        return default
    result = round(number)
    if not low <= result <= high:
        row.error(f"{label} must be between {low} and {high} (got {result}).")
        return default
    return result


def _names(row: ParsedRow, values: dict) -> None:
    first = str(values.get("first_name", "")).strip()
    last = str(values.get("last_name", "")).strip()
    if not (first and last) and "name" in values:
        parts = str(values["name"]).strip().split(None, 1)
        if len(parts) == 2:
            first, last = first or parts[0], last or parts[1]
    if not first or not last:
        row.error("First and last name are required.")
    for label, value in (("First name", first), ("Last name", last)):
        if len(value) > 40:
            row.error(f"{label} is longer than 40 characters.")
    row.first_name, row.last_name = first, last


def _position(row: ParsedRow, values: dict) -> None:
    raw = str(values.get("position", "")).strip().upper()
    if not raw:
        row.error("Position is required.")
        return
    if raw in Position.__members__:
        row.position = Position(raw)
    elif raw in POSITION_ALIASES:
        row.position = POSITION_ALIASES[raw]
    else:
        row.error(f"Unknown position {raw!r}.")


def _height(row: ParsedRow, value: Any) -> int:
    if not _present(value):
        return row.height_in
    text = str(value).strip().lower()
    match = re.fullmatch(r"(\d)\s*(?:'|ft|-|\s)\s*(\d{1,2})?\s*(?:\"|''|in)?", text)
    if match:
        inches = int(match.group(1)) * 12 + int(match.group(2) or 0)
    else:
        number = _to_number(value)
        if number is None:
            row.error(f"Height must be inches (74) or feet-inches (6-2), got {value!r}.")
            return row.height_in
        inches = round(number)
    if not 60 <= inches <= 90:
        row.error(f"Height must be between 60 and 90 inches (got {inches}).")
        return row.height_in
    return inches


def _choice(row: ParsedRow, values: dict, key: str, label: str, options: tuple[str, ...],
            default: str) -> str:
    if key not in values:
        return default
    text = normalize_header(values[key])
    if text == "ir":
        text = "injured_reserve"
    if text in options:
        return text
    row.warn(f"{label} {values[key]!r} not recognized; using {default!r}.")
    return default


def _ratings(row: ParsedRow, values: dict) -> None:
    given: dict[str, int] = {}
    for name in ATTRIBUTES:
        if name not in values:
            continue
        number = _to_number(values[name])
        if number is None or number < 0:
            row.error(f"{name} must be a rating from 0 to 99 (got {values[name]!r}).")
            continue
        value = round(number)
        if value > RATING_MAX:
            row.warn(f"{name} {value} capped at {RATING_MAX}.")
            value = RATING_MAX
        given[name] = value

    listed_overall = _int_field(row, values, "overall", "Overall", 0, 99)
    if row.position is None:
        row.ratings = given
        return

    weights = POSITION_WEIGHTS[row.position]
    missing_keys = [name for name in weights if name not in given]
    fill = DEFAULT_RATING
    if listed_overall is not None and missing_keys:
        fill = _fill_for_overall(listed_overall, weights, given, missing_keys)
    row.ratings = {
        name: given.get(name, fill if name in weights else DEFAULT_RATING)
        for name in ATTRIBUTES
    }
    row.overall = calculate_overall(row.position, row.ratings)
    if listed_overall is not None and abs(listed_overall - row.overall) > 2:
        row.warn(f"Listed overall {listed_overall} differs from the {row.overall} calculated "
                 f"from ratings; using {row.overall}.")

    potential = _int_field(row, values, "potential", "Potential", 0, 99)
    row.potential = max(potential if potential is not None else row.overall, row.overall)


def _fill_for_overall(overall: int, weights: dict[str, float], given: dict[str, int],
                      missing: list[str]) -> int:
    """Rating for the missing key attributes that makes the position OVR equal `overall`,
    given the key attributes the file did provide."""
    total = sum(weights.values())
    provided = sum(weights[name] * given[name] for name in weights if name in given)
    missing_weight = sum(weights[name] for name in missing)
    return max(0, min(RATING_MAX, round((overall * total - provided) / missing_weight)))
