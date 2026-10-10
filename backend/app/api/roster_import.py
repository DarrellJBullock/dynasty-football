from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.teams import get_team
from app.db import get_db
from app.models import Team
from app.roster_import.readers import MAX_FILE_BYTES, FileFormat, ImportFileError
from app.roster_import.templates import build_template
from app.roster_import.writers import MEDIA_TYPES
from app.schemas import ImportMode, ImportPreview, ImportResult
from app.services import roster_export, roster_import
from app.services.teams import load_overrides, load_roster, team_detail

router = APIRouter(tags=["roster import & export"])


def _plan(db: Session, team: Team, file: UploadFile, mode: ImportMode):
    content = file.file.read(MAX_FILE_BYTES + 1)
    try:
        return roster_import.plan_import(db, team, file.filename or "", content, mode)
    except ImportFileError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/teams/{team_id}/roster-import/preview", response_model=ImportPreview)
def preview_import(
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = "append",
    team: Team = Depends(get_team),
    db: Session = Depends(get_db),
):
    """Validate a roster file against the team without changing anything."""
    return roster_import.preview(_plan(db, team, file, mode), team)


@router.post("/teams/{team_id}/roster-import/commit", response_model=ImportResult)
def commit_import(
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = "append",
    skip_invalid: Annotated[bool, Form()] = False,
    team: Team = Depends(get_team),
    db: Session = Depends(get_db),
):
    """Import the file. All-or-nothing unless skip_invalid is set."""
    plan = _plan(db, team, file, mode)
    with roster_errors(db):
        imported, released, skipped = roster_import.commit(db, team, plan, skip_invalid)
    return ImportResult(imported=imported, released=released, skipped=skipped,
                        team=team_detail(team, load_roster(db, team.id),
                                         load_overrides(db, [team.id])[team.id]))


@router.get("/roster-import/template.{fmt}")
def download_template(fmt: FileFormat):
    return Response(
        content=build_template(fmt),
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="roster-template.{fmt.value}"'},
    )


@router.get("/teams/{team_id}/roster-export.{fmt}")
def export_roster(fmt: FileFormat, team: Team = Depends(get_team),
                  db: Session = Depends(get_db)):
    """Download the roster in the import format (re-importing it reproduces the roster)."""
    content, filename = roster_export.export_roster(db, team, fmt)
    return Response(
        content=content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
