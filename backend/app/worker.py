"""The background job worker: `python -m app.worker`.

Claims queued jobs one at a time and runs them (`services.jobs`), and fails jobs whose
worker died. Run as many as you like; `SKIP LOCKED` keeps them off each other's jobs.
In development and e2e the API can run one in a thread instead (`WORKER_EMBEDDED=1`).
"""

import logging
import signal
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.observability import configure_logging, init_sentry
from app.services import jobs

log = logging.getLogger("app.worker")

Sessions = Callable[[], AbstractContextManager[Session]]  # a new session per job

IDLE_WAIT = 0.5  # seconds between looks at the queue when it's empty
REAP_EVERY = 30.0  # seconds between sweeps for jobs whose worker died


def run_once(session: Sessions = SessionLocal) -> bool:
    """Claim and run one job. Returns whether there was one."""
    with session() as db:
        job = jobs.claim(db)
        if job is None:
            return False
        fields = {"job_id": job.id, "kind": job.kind, "league_id": job.league_id}
        log.info("job %s (%s) started for league %s", job.id, job.kind, job.league_id,
                 extra=fields)
        started = time.monotonic()
        try:
            jobs.run(db, job)
        except Exception:  # recorded on the job by run(); keep working
            log.exception("job %s failed", job.id, extra=fields)
        log.info("job %s %s", job.id, job.status, extra={
            **fields, "status": job.status, "progress": job.progress, "total": job.total,
            "duration_ms": round((time.monotonic() - started) * 1000)})
        return True


def work(stop: threading.Event, session: Sessions = SessionLocal) -> None:
    """Run jobs until `stop` is set (between jobs)."""
    last_reap = 0.0
    while not stop.is_set():
        try:
            if time.monotonic() - last_reap > REAP_EVERY:
                with session() as db:
                    if reaped := jobs.reap_stale(db):
                        log.warning("failed %s stale job(s)", reaped)
                last_reap = time.monotonic()
            if not run_once(session):
                stop.wait(IDLE_WAIT)
        except Exception:  # e.g. the database is restarting: wait and carry on
            log.exception("worker error")
            stop.wait(5)


def start_thread() -> threading.Event:
    """Run a worker in a daemon thread (the API's embedded worker). Set the event to stop."""
    stop = threading.Event()
    threading.Thread(target=work, args=(stop,), name="job-worker", daemon=True).start()
    return stop


def main() -> None:
    configure_logging()
    init_sentry("worker")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("worker started")
    work(stop)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
