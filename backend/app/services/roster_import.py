"""Roster import: preview a file against a team's roster, then commit it.

Preview and commit both re-read the uploaded file, so the server holds no state
between the two steps.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.contracts import market_salary
from app.domain.positions import ROSTER_MAX, available_jersey
from app.models import Player, Team
from app.roster_import.readers import detect_format, read_rows
from app.roster_import.rows import ParsedRow, parse_rows
from app.schemas import (
    ImportMessage,
    ImportMode,
    ImportPreview,
    ImportRow,
    ImportSummary,
)
from app.services.errors import RosterError
from app.services.roster import new_player, release_player, season_year
from app.services.teams import load_roster, payroll


@dataclass
class ImportPlan:
    format: str
    mode: ImportMode
    rows: list[ParsedRow]
    file_warnings: list[str]
    current: list[Player]  # roster before import
    kept: list[Player]  # players who stay (append mode) — empty when replacing

    @property
    def valid_rows(self) -> list[ParsedRow]:
        return [row for row in self.rows if row.is_valid]


def plan_import(db: Session, team: Team, filename: str, content: bytes,
                mode: ImportMode) -> ImportPlan:
    fmt = detect_format(filename)
    parsed = parse_rows(read_rows(content, fmt))
    current = load_roster(db, team.id)
    kept = current if mode == "append" else []
    plan = ImportPlan(format=fmt.value, mode=mode, rows=parsed.rows,
                      file_warnings=parsed.warnings, current=current, kept=kept)

    capacity = ROSTER_MAX - len(kept)
    taken = {p.jersey_number for p in kept}
    for row in plan.rows:
        if not row.is_valid:
            continue
        if capacity <= 0:
            row.error(f"Roster would exceed {ROSTER_MAX} players.")
            continue
        capacity -= 1
        assert row.position is not None and row.overall is not None
        if row.jersey_number is None:
            row.jersey_number = available_jersey(row.position, taken)
        elif row.jersey_number in taken:
            assigned = available_jersey(row.position, taken)
            row.warn(f"Jersey #{row.jersey_number} is taken; assigned #{assigned}.")
            row.jersey_number = assigned
        taken.add(row.jersey_number)
        if row.salary is None:
            row.salary = market_salary(row.position, row.overall)

    payroll_after = _payroll_after(plan)
    if payroll_after > team.league.salary_cap:
        over = payroll_after - team.league.salary_cap
        plan.file_warnings.append(
            f"Payroll after import exceeds the salary cap by ${over:,}. Imports are allowed "
            "over the cap, but the team can't sign free agents until it's back under.")
    return plan


def _payroll_after(plan: ImportPlan) -> int:
    return payroll(plan.kept) + sum(row.salary or 0 for row in plan.valid_rows)


def _row_out(row: ParsedRow) -> ImportRow:
    status = ("error" if not row.is_valid
              else "warning" if row.messages else "ok")
    return ImportRow(
        row_number=row.row_number, status=status, first_name=row.first_name,
        last_name=row.last_name, position=row.position, jersey_number=row.jersey_number,
        age=row.age, height_in=row.height_in, weight_lb=row.weight_lb, college=row.college,
        overall=row.overall, potential=row.potential, salary=row.salary,
        messages=[ImportMessage(level=m.level, message=m.message) for m in row.messages],
    )


def preview(plan: ImportPlan, team: Team) -> ImportPreview:
    rows = [_row_out(row) for row in plan.rows]
    errors = sum(1 for r in rows if r.status == "error")
    valid = len(rows) - errors
    return ImportPreview(
        format=plan.format,
        mode=plan.mode,
        file_warnings=plan.file_warnings,
        rows=rows,
        summary=ImportSummary(total=len(rows), valid=valid,
                              warnings=sum(1 for r in rows if r.status == "warning"),
                              errors=errors),
        roster_before=len(plan.current),
        released=len(plan.current) - len(plan.kept),
        roster_after=len(plan.kept) + valid,
        roster_max=ROSTER_MAX,
        payroll_after=_payroll_after(plan),
        salary_cap=team.league.salary_cap,
        can_commit=errors == 0 and valid > 0,
    )


def commit(db: Session, team: Team, plan: ImportPlan, skip_invalid: bool) -> tuple[int, int, int]:
    """Apply the plan. Returns (imported, released, skipped)."""
    valid = plan.valid_rows
    skipped = len(plan.rows) - len(valid)
    if skipped and not skip_invalid:
        raise RosterError(f"{skipped} row(s) have errors. Fix the file, or choose to skip "
                          "invalid rows.", 422)
    if not valid:
        raise RosterError("No valid rows to import.", 422)

    released = 0
    if plan.mode == "replace":
        for player in plan.current:
            release_player(db, player)
            released += 1

    year = season_year(db, team)
    for row in valid:
        assert row.position is not None and row.salary is not None
        db.add(new_player(
            team,
            season_year=year,
            ratings=row.ratings,
            salary=row.salary,
            contract_years=row.contract_years,
            potential=row.potential,
            first_name=row.first_name,
            last_name=row.last_name,
            position=row.position.value,
            jersey_number=row.jersey_number,
            age=row.age,
            height_in=row.height_in,
            weight_lb=row.weight_lb,
            college=row.college,
            years_pro=row.years_pro,
            development_trait=row.development_trait,
            injury_status=row.injury_status,
        ))
    db.flush()
    return len(valid), released, skipped

