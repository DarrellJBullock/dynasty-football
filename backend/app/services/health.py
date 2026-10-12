"""Readiness: can this instance serve? The database must answer, and its schema must be
at the newest migration this build knows (deploys run migrations before starting)."""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def expected_revision() -> str | None:
    """The newest migration in this build."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def readiness(db: Session) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        current = MigrationContext.configure(db.connection()).get_current_revision()
    except Exception as exc:  # noqa: BLE001 (any failure means not ready)
        return {"status": "unavailable", "detail": f"database: {type(exc).__name__}"}
    expected = expected_revision()
    if current != expected:
        return {"status": "migrating", "detail": f"schema at {current}, expected {expected}"}
    return {"status": "ready", "revision": current or ""}
