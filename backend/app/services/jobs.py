"""Background jobs: the long simulations, run by a worker (`app.worker`) with progress.

The API queues a job (`enqueue`); a worker claims the oldest queued one (`claim`) and runs
it (`run`) with the same service code as the synchronous endpoints and the same seeds, so
a job plays exactly the games a request would. A run commits after every week (playoff
round, market day), recording its progress, so the league is always at a clean boundary:
a cancel stops there, and a crash loses only the step in progress. One job per league at a
time; while it's queued or running the league's other changes are refused (`api.locks`).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.free_agency import MARKET_DAYS
from app.models import Job, League, Season
from app.schemas import SimulateRequest
from app.services import draft, free_agency, offseason, playoffs
from app.services import season as season_service
from app.services.errors import RosterError
from app.services.teams import current_season

STALE_AFTER = timedelta(minutes=1)  # a running job with no heartbeat this long has died


class JobCancelled(Exception):
    """Raised between steps when the job was asked to stop."""


Step = Callable[[str, bool], None]  # (label of the step just done, more to come)
Runner = Callable[[Session, Season, Step], dict]


def _now() -> datetime:
    return datetime.now(UTC)


def _sim_regular_season(db: Session, season: Season, step: Step) -> dict:
    steps, played = season_service.simulate(
        db, season, SimulateRequest(until="end_of_regular_season"), on_step=step)
    return season_service.simulation_result(db, season, steps, played).model_dump(mode="json")


def _sim_playoffs(db: Session, season: Season, step: Step) -> dict:
    steps, played = season_service.simulate(
        db, season, SimulateRequest(until="end_of_playoffs"), on_step=step)
    return season_service.simulation_result(db, season, steps, played).model_dump(mode="json")


def _advance_offseason(db: Session, season: Season, step: Step) -> dict:
    new_season = offseason.advance(db, season)
    return season_service.season_view(db, new_season).model_dump(mode="json")


def _finish_free_agency(db: Session, season: Season, step: Step) -> dict:
    entries = free_agency.play_days(db, season, "end", on_step=step)
    return free_agency.play_result(db, season, entries).model_dump(mode="json")


def _finish_draft(db: Session, season: Season, step: Step) -> dict:
    picks = draft.play(db, season, "end")
    return draft.play_result(db, season, picks).model_dump(mode="json")


KINDS: dict[str, Runner] = {
    "sim_regular_season": _sim_regular_season,
    "sim_playoffs": _sim_playoffs,
    "advance_offseason": _advance_offseason,
    "finish_free_agency": _finish_free_agency,
    "finish_draft": _finish_draft,
}

LABELS = {  # what the progress bar says before the first step is done
    "sim_regular_season": "Simulating the season",
    "sim_playoffs": "Simulating the playoffs",
    "advance_offseason": "Running the offseason",
    "finish_free_agency": "Playing free agency",
    "finish_draft": "Finishing the draft",
}


def _total(db: Session, season: Season, kind: str) -> int:
    """How many steps the job will take (for the progress bar)."""
    if kind == "sim_regular_season":
        return max(1, season_service.season_weeks(db, season.id) - season.current_week + 1)
    if kind == "sim_playoffs":
        return max(1, playoffs.rounds_left(db, season))
    if kind == "finish_free_agency":
        return max(1, MARKET_DAYS - (season.free_agency_day or 1) + 1)
    return 1


def enqueue(db: Session, league: League, kind: str) -> Job:
    """Queue a job for the league (committed). 409 if one is already queued or running."""
    if kind not in KINDS:
        raise RosterError(f"Unknown job: {kind}", 422)
    if season_service.active_job(db, league.id) is not None:
        raise RosterError("A simulation is already running in this league.")
    season = current_season(db, league.id)
    if season is None:
        raise RosterError("The league has no season.", 404)
    job = Job(league_id=league.id, kind=kind, total=_total(db, season, kind),
              label=LABELS[kind])
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:  # another request queued one first
        db.rollback()
        raise RosterError("A simulation is already running in this league.") from exc
    return job


def claim(db: Session) -> Job | None:
    """Take the oldest queued job and mark it running (committed); None if there's none.
    `SKIP LOCKED` lets several workers claim side by side without taking the same job."""
    job = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.id)
                    .limit(1).with_for_update(skip_locked=True))
    if job is None:
        db.rollback()
        return None
    return begin(db, job)


def begin(db: Session, job: Job) -> Job:
    """Mark a job running (committed)."""
    job.status = "running"
    job.started_at = job.heartbeat_at = _now()
    db.commit()
    return job


def run(db: Session, job: Job) -> Job:
    """Run a claimed job to the end, recording progress after each step and how it ended."""
    season = current_season(db, job.league_id)

    def step(label: str, more: bool) -> None:
        job.progress = min(job.total, job.progress + 1)
        job.label = label
        job.heartbeat_at = _now()
        db.commit()  # the step's games and the progress together
        if more and db.scalar(select(Job.cancel_requested).where(Job.id == job.id)):
            raise JobCancelled

    try:
        if season is None:
            raise RosterError("The league has no season.", 404)
        result = KINDS[job.kind](db, season, step)
    except JobCancelled:
        _finish(db, job, "cancelled")
    except RosterError as exc:
        db.rollback()
        _finish(db, job, "failed", error=exc.message)
    except Exception as exc:  # noqa: BLE001 (record it, and keep the worker alive)
        db.rollback()
        _finish(db, job, "failed", error=f"The simulation failed: {exc}"[:500])
        raise
    else:
        job.result = result
        job.progress = job.total
        _finish(db, job, "done")
    return job


def _finish(db: Session, job: Job, status: str, error: str | None = None) -> None:
    job.status = status
    job.error = error
    job.finished_at = _now()
    db.commit()


def cancel(db: Session, job: Job) -> Job:
    """Ask a job to stop: a queued one stops at once, a running one after its current step
    (one-step jobs can't be stopped once they've started)."""
    if job.status == "queued":
        job.cancel_requested = True
        _finish(db, job, "cancelled")
    elif job.status == "running":
        job.cancel_requested = True
        db.commit()
    return job


def reap_stale(db: Session, now: datetime | None = None) -> int:
    """Fail running jobs whose worker stopped sending heartbeats, unlocking their leagues."""
    cutoff = (now or _now()) - STALE_AFTER
    result = db.execute(update(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)
                        .values(status="failed", finished_at=now or _now(),
                                error="The simulation stopped unexpectedly. Try again."))
    db.commit()
    return result.rowcount
