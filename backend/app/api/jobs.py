from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import roster_errors
from app.api.leagues import get_league
from app.config import get_settings
from app.db import get_db
from app.models import Job, League
from app.schemas import JobOut, JobRequest
from app.services import jobs as job_service
from app.services.serializers import job_out

router = APIRouter(tags=["jobs"])


def jobs_inline() -> bool:
    """Run jobs inside the request instead of queueing them for a worker (tests)."""
    return get_settings().jobs_inline


def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.post("/leagues/{league_id}/jobs", response_model=JobOut, status_code=202)
def start_job(request: JobRequest, league: League = Depends(get_league),
              db: Session = Depends(get_db), inline: bool = Depends(jobs_inline)):
    """Start a long simulation in the background: the rest of the regular season, the
    playoffs, the offseason, or finishing free agency or the draft. Poll the job for its
    progress; its `result` is what the matching synchronous endpoint would have returned."""
    with roster_errors(db):
        job = job_service.enqueue(db, league, request.kind)
    if inline:
        job_service.run(db, job_service.begin(db, job))
    return job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job: Job = Depends(get_job)):
    """A job's status and progress, and its result once it's done."""
    return job_out(job)


@router.delete("/jobs/{job_id}", response_model=JobOut)
def cancel_job(job: Job = Depends(get_job), db: Session = Depends(get_db)):
    """Stop a job: a queued one at once, a running one after the week (round, day) it's on.
    The offseason and the draft run as one step and finish once started."""
    return job_out(job_service.cancel(db, job))
