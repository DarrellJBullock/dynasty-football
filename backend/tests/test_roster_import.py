import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.domain.positions import ROSTER_MAX, Position
from app.models import Franchise
from app.roster_import.readers import FileFormat, ImportFileError, detect_format, read_rows
from app.roster_import.rows import parse_row, parse_rows


def csv_bytes(rows: list[dict], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def xlsx_bytes(rows: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(rows[0]))
    for row in rows:
        sheet.append(list(row.values()))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def player(first="Test", last="Player", position="WR", **extra) -> dict:
    return {"first_name": first, "last_name": last, "position": position, **extra}


# ---------- readers ----------

class TestReaders:
    def test_detect_format(self):
        assert detect_format("Roster.CSV") is FileFormat.CSV
        assert detect_format("team.xlsx") is FileFormat.XLSX
        assert detect_format("team.json") is FileFormat.JSON
        with pytest.raises(ImportFileError, match="xls"):
            detect_format("old.xls")
        with pytest.raises(ImportFileError, match="Unsupported"):
            detect_format("roster.pdf")

    def test_csv_with_bom_and_semicolons(self):
        content = "﻿".encode() + csv_bytes([player(), player("A", "B")], delimiter=";")
        rows = read_rows(content, FileFormat.CSV)
        assert rows[0]["first_name"] == "Test"
        assert len(rows) == 2

    def test_xlsx_skips_blank_rows(self):
        content = xlsx_bytes([player(), {"first_name": None, "last_name": None, "position": None}])
        assert len(read_rows(content, FileFormat.XLSX)) == 1

    def test_json_list_object_and_nested_ratings(self):
        nested = {"players": [{**player(), "ratings": {"speed": 91},
                               "contract": {"salary": 2_000_000, "years": 3}}]}
        rows = read_rows(json.dumps(nested).encode(), FileFormat.JSON)
        assert rows[0]["speed"] == 91
        assert rows[0]["salary"] == 2_000_000
        assert rows[0]["contract_years"] == 3
        assert read_rows(json.dumps([player()]).encode(), FileFormat.JSON)[0]["position"] == "WR"

    @pytest.mark.parametrize("content, fmt, message", [
        (b"", FileFormat.CSV, "empty"),
        (b"{not json", FileFormat.JSON, "Invalid JSON"),
        (b'{"teams": []}', FileFormat.JSON, "list of players"),
        (b"not a zip", FileFormat.XLSX, "Excel"),
        (b"first_name,last_name\n", FileFormat.CSV, "No player rows"),
    ])
    def test_unreadable_files(self, content, fmt, message):
        with pytest.raises(ImportFileError, match=message):
            read_rows(content, fmt)

    def test_too_many_rows(self):
        content = csv_bytes([player(str(i)) for i in range(501)])
        with pytest.raises(ImportFileError, match="Too many rows"):
            read_rows(content, FileFormat.CSV)


# ---------- row parsing ----------

class TestRows:
    def test_header_and_position_aliases(self):
        parsed = parse_rows([{"First Name": "Ty", "Surname": "Ross", "POS": "lt", "#": "71",
                              "Ht": "6-5", "Wt": 310, "SPD": 60, "Mystery": "x"}])
        row = parsed.rows[0]
        assert row.is_valid, row.messages
        assert (row.first_name, row.last_name, row.position) == ("Ty", "Ross", Position.OT)
        assert row.jersey_number == 71
        assert row.height_in == 77
        assert row.ratings["speed"] == 60
        assert parsed.warnings == ["Ignored unrecognized column(s): Mystery."]

    def test_full_name_column_is_split(self):
        row = parse_rows([{"name": "Jalen De La Cruz", "pos": "QB"}]).rows[0]
        assert (row.first_name, row.last_name) == ("Jalen", "De La Cruz")

    @pytest.mark.parametrize("height, inches", [("74", 74), ("6'2\"", 74), ("6 ft 1 in", 73),
                                                (75.0, 75), ("6-0", 72)])
    def test_heights(self, height, inches):
        assert parse_row(1, {**player(), "height_in": height}).height_in == inches

    def test_missing_ratings_default_to_50(self):
        row = parse_row(1, player(position="CB"))
        assert row.ratings["speed"] == 50
        assert row.overall == 50

    def test_overall_only_rows_get_matching_key_attributes(self):
        row = parse_row(1, player(position="QB", overall=88))
        assert row.overall == 88
        assert row.ratings["throw_accuracy"] == 88
        assert row.ratings["tackling"] == 50
        assert not row.messages

    def test_overall_with_some_key_ratings_fills_the_rest_to_match(self):
        row = parse_row(1, player(position="RB", overall=81, speed=94))
        assert row.ratings["speed"] == 94
        assert row.overall == 81
        assert not row.messages

    def test_impossible_listed_overall_warns(self):
        # Even with every other key attribute at 99, a K can't reach 90 with 20 power.
        row = parse_row(1, player(position="K", overall=90, kick_power=20))
        assert row.ratings["kick_accuracy"] == 99
        assert row.overall < 88
        assert "differs" in row.messages[0].message

    def test_listed_overall_that_disagrees_with_ratings_warns(self):
        row = parse_row(1, player(position="K", overall=90, kick_power=60, kick_accuracy=60))
        assert row.overall == 60
        assert row.is_valid
        assert "differs" in row.messages[0].message

    def test_ratings_above_99_are_capped_with_warning(self):
        row = parse_row(1, player(speed="104"))
        assert row.ratings["speed"] == 99
        assert row.messages[0].level == "warning"

    @pytest.mark.parametrize("field, value, fragment", [
        ("position", "LS", "Unknown position"),
        ("jersey_number", 120, "Jersey #"),
        ("age", "old", "Age must be a number"),
        ("height_in", "tall", "Height"),
        ("speed", -5, "speed must be a rating"),
        ("weight_lb", 90, "Weight"),
    ])
    def test_invalid_values_are_row_errors(self, field, value, fragment):
        row = parse_row(1, {**player(), field: value})
        assert not row.is_valid
        assert any(fragment in m.message for m in row.messages)

    def test_missing_name_and_position(self):
        row = parse_row(1, {"jersey_number": 5})
        messages = " ".join(m.message for m in row.messages)
        assert "name" in messages and "Position is required" in messages

    def test_unknown_trait_and_status_fall_back_with_warning(self):
        row = parse_row(1, player(development_trait="Superstar", injury_status="IR"))
        assert row.development_trait == "normal"
        assert row.injury_status == "injured_reserve"
        assert row.is_valid
        assert len(row.messages) == 1

    def test_potential_never_below_overall(self):
        assert parse_row(1, player(position="QB", overall=80, potential=60)).potential == 80


# ---------- API ----------

def _preview(client: TestClient, team_id: int, content: bytes, filename="roster.csv",
             mode="append"):
    return client.post(f"/api/teams/{team_id}/roster-import/preview",
                       files={"file": (filename, content)}, data={"mode": mode})


def _commit(client: TestClient, team_id: int, content: bytes, filename="roster.csv",
            mode="append", skip_invalid=False):
    return client.post(f"/api/teams/{team_id}/roster-import/commit",
                       files={"file": (filename, content)},
                       data={"mode": mode, "skip_invalid": str(skip_invalid).lower()})


@pytest.fixture
def team_id(franchise: Franchise) -> int:
    return franchise.team_id


def _release(client: TestClient, team_id: int, count: int) -> list[dict]:
    roster = client.get(f"/api/teams/{team_id}/roster").json()
    for p in roster[-count:]:
        client.post(f"/api/players/{p['id']}/release")
    return roster


class TestImportApi:
    @pytest.mark.parametrize("fmt", ["csv", "xlsx", "json"])
    def test_templates_round_trip(self, client: TestClient, team_id: int, fmt: str):
        template = client.get(f"/api/roster-import/template.{fmt}")
        assert template.status_code == 200
        assert f"roster-template.{fmt}" in template.headers["content-disposition"]
        body = _preview(client, team_id, template.content, f"t.{fmt}", "replace").json()
        assert body["summary"] == {"total": 2, "valid": 2, "warnings": 0, "errors": 0}
        assert body["can_commit"] is True

    def test_preview_changes_nothing(self, client: TestClient, team_id: int):
        before = client.get(f"/api/teams/{team_id}/roster").json()
        _preview(client, team_id, csv_bytes([player()]), mode="replace")
        assert client.get(f"/api/teams/{team_id}/roster").json() == before

    def test_append_to_full_roster_is_blocked_per_row(self, client: TestClient, team_id: int):
        body = _preview(client, team_id, csv_bytes([player()])).json()
        assert body["rows"][0]["status"] == "error"
        assert "exceed 53" in body["rows"][0]["messages"][0]["message"]
        assert body["can_commit"] is False

    def test_append_fills_open_spots_and_reassigns_jerseys(self, client: TestClient,
                                                          team_id: int):
        roster = _release(client, team_id, 2)
        taken = roster[0]["jersey_number"]
        content = csv_bytes([player("New", "One", "WR", jersey_number=taken, speed=90),
                             player("New", "Two", "CB")])
        preview = _preview(client, team_id, content).json()
        assert preview["roster_after"] == ROSTER_MAX
        first, second = preview["rows"]
        assert first["status"] == "warning"
        assert first["jersey_number"] != taken
        assert second["jersey_number"] is not None

        result = _commit(client, team_id, content).json()
        assert (result["imported"], result["released"], result["skipped"]) == (2, 0, 0)
        assert result["team"]["roster_count"] == ROSTER_MAX
        numbers = [p["jersey_number"] for p in client.get(f"/api/teams/{team_id}/roster").json()]
        assert len(numbers) == len(set(numbers))

    def test_replace_releases_current_roster(self, client: TestClient, team_id: int, league):
        before = client.get(f"/api/teams/{team_id}/roster").json()
        content = xlsx_bytes([player("Only", "Guy", "QB", overall=75, salary=1_000_000)])
        result = _commit(client, team_id, content, "r.xlsx", "replace").json()
        assert result["released"] == len(before)
        assert result["imported"] == 1
        roster = client.get(f"/api/teams/{team_id}/roster").json()
        assert [p["full_name"] for p in roster] == ["Only Guy"]
        assert roster[0]["overall"] == 75
        assert roster[0]["contract"]["salary"] == 1_000_000
        free_agents = client.get(f"/api/leagues/{league.id}/free-agents").json()
        assert before[0]["id"] in {p["id"] for p in free_agents}

    def test_commit_is_all_or_nothing_by_default(self, client: TestClient, team_id: int):
        content = csv_bytes([player("Good", "Row"), player("Bad", "Row", "XX")])
        before = client.get(f"/api/teams/{team_id}/roster").json()
        response = _commit(client, team_id, content, mode="replace")
        assert response.status_code == 422
        assert "1 row(s) have errors" in response.json()["detail"]
        assert client.get(f"/api/teams/{team_id}/roster").json() == before

    def test_skip_invalid_imports_the_good_rows(self, client: TestClient, team_id: int):
        content = csv_bytes([player("Good", "Row"), player("Bad", "Row", "XX")])
        result = _commit(client, team_id, content, mode="replace", skip_invalid=True).json()
        assert (result["imported"], result["skipped"]) == (1, 1)

    def test_over_cap_import_is_allowed_with_warning(self, client: TestClient, team_id: int):
        content = csv_bytes([player(salary=400_000_000)])
        body = _preview(client, team_id, content, mode="replace").json()
        assert body["can_commit"] is True
        assert any("exceeds the salary cap" in w for w in body["file_warnings"])

    def test_more_than_53_rows_in_replace_mode(self, client: TestClient, team_id: int):
        rows = [player(f"P{i}", "Depth", "WR") for i in range(55)]
        body = _preview(client, team_id, csv_bytes(rows), mode="replace").json()
        assert body["summary"]["valid"] == ROSTER_MAX
        assert body["summary"]["errors"] == 2
        assert body["roster_after"] == ROSTER_MAX

    def test_bad_files_are_rejected(self, client: TestClient, team_id: int):
        assert _preview(client, team_id, b"x", "roster.pdf").status_code == 422
        response = _preview(client, team_id, b"{oops", "roster.json")
        assert response.status_code == 422
        assert "Invalid JSON" in response.json()["detail"]
        too_big = b"a" * (2 * 1024 * 1024 + 10)
        assert "larger than" in _preview(client, team_id, too_big).json()["detail"]

    def test_invalid_mode_and_unknown_team(self, client: TestClient, team_id: int):
        assert _preview(client, team_id, csv_bytes([player()]), mode="merge").status_code == 422
        assert _preview(client, 999999, csv_bytes([player()])).status_code == 404
        assert client.get("/api/roster-import/template.pdf").status_code == 422

    def test_replace_import_clears_saved_depth_chart(self, client: TestClient, team_id: int):
        chart = client.get(f"/api/teams/{team_id}/depth-chart").json()
        qbs = [p["id"] for p in next(s for s in chart["slots"] if s["slot"] == "QB")["players"]]
        client.put(f"/api/teams/{team_id}/depth-chart/QB", json={"player_ids": qbs[::-1]})

        content = csv_bytes([player("New", "Starter", "QB", overall=70)])
        result = _commit(client, team_id, content, mode="replace").json()

        chart = client.get(f"/api/teams/{team_id}/depth-chart").json()
        qb = next(s for s in chart["slots"] if s["slot"] == "QB")
        assert [p["full_name"] for p in qb["players"]] == ["New Starter"]
        assert qb["starter_ids"] == [qb["players"][0]["id"]]
        assert result["team"]["ratings"] == chart["team"]["ratings"]


def test_csv_quoted_fields_with_embedded_quotes_and_delimiters():
    content = (b'first_name,last_name,position,college\n'
               b'Ty,"O\'Neil, Jr.",QB,"The ""U"" of Somewhere"\n')
    row = read_rows(content, FileFormat.CSV)[0]
    assert row["last_name"] == "O'Neil, Jr."
    assert row["college"] == 'The "U" of Somewhere'
