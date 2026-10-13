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
from app.models import Job, League, Season, Team
from app.schemas import SimulateRequest
from app.services import draft, free_agency, offseason, playoffs
from app.services import season as season_service
from app.services.errors import RosterError
from app.services.members import human_team_ids
from app.services.teams import current_season

STALE_AFTER = timedelta(minutes=1)  # a running job with no heartbeat this long has died


class JobCancelled(Exception):
    """Raised between steps when the job was asked to stop."""


Step = Callable[[str, bool], None]  # (label of the step just done, more to come)
Runner = Callable[[Session, Season, Step, dict], dict]  # (…, the job's params)


def _now() -> datetime:
    return datetime.now(UTC)


def _sim_regular_season(db: Session, season: Season, step: Step, params: dict) -> dict:
    steps, played = season_service.simulate(
        db, season, SimulateRequest(until="end_of_regular_season"), on_step=step)
    return season_service.simulation_result(
        db, season, steps, played, params.get("team_id")).model_dump(mode="json")


def _sim_playoffs(db: Session, season: Season, step: Step, params: dict) -> dict:
    steps, played = season_service.simulate(
        db, season, SimulateRequest(until="end_of_playoffs"), on_step=step)
    return season_service.simulation_result(
        db, season, steps, played, params.get("team_id")).model_dump(mode="json")


def _advance_offseason(db: Session, season: Season, step: Step, _params: dict) -> dict:
    new_season = offseason.advance(db, season)
    return season_service.season_view(db, new_season).model_dump(mode="json")


def _finish_free_agency(db: Session, season: Season, step: Step, params: dict) -> dict:
    entries = free_agency.play_days(db, season, "end", on_step=step)
    return free_agency.play_result(
        db, season, entries, params.get("team_id")).model_dump(mode="json")


def _finish_draft(db: Session, season: Season, step: Step, _params: dict) -> dict:
    picks = draft.play(db, season, "end")
    return draft.play_result(db, season, picks).model_dump(mode="json")


def _sim_seasons(db: Session, season: Season, step: Step, params: dict) -> dict:
    """Sim ahead: play on, season after season, with the franchise on autopilot through
    every offseason (it re-signs, bids, drafts and cuts to 53 like an AI team), until the
    preseason `params["seasons"]` seasons on. Returns the seasons played, for the Dynasty
    report (services/dynasty.py)."""
    count, league_id, first_year = params["seasons"], season.league_id, season.year
    humans = [db.get(Team, team_id) for team_id in sorted(human_team_ids(db, league_id))]
    done = 0
    while done < count:
        season = current_season(db, league_id)
        # Free agency and the draft belong to the next season's row, but they finish the
        # offseason of the one just played: label them with its year.
        year = season.year - 1 if season.phase in ("free_agency", "draft") else season.year
        prefix = f"Season {done + 1} of {count} · {year}"

        def inner(what: str = "", prefix: str = prefix) -> Step:
            """Steps inside a phase: there's always more to come (the offseason)."""
            return lambda label, _more: step(f"{prefix} · {what}{label}", True)

        if season.phase in ("preseason", "regular_season"):
            for team in humans:
                draft.cut_down(db, team)  # (to 53, if the roster is over)
            season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"),
                                    on_step=inner())
        elif season.phase == "playoffs":
            season_service.simulate(db, season, SimulateRequest(until="end_of_playoffs"),
                                    on_step=inner())
        elif season.phase == "offseason":
            offseason.advance(db, season, autopilot=True)
            step(f"{prefix} · Offseason", True)
        elif season.phase == "free_agency":
            free_agency.play_days(db, season, "end", on_step=inner("Free agency, "),
                                  autopilot=True)
        elif season.phase == "draft":
            draft.draft_view(db, season.league)  # (generates the class if it isn't there)
            draft.play(db, season, "end", autopilot=True)
            done += 1
            step(f"{prefix} · Draft", done < count)
        else:  # (no other phases; never loop on one)
            raise RosterError(f"Can't sim ahead from the {season.phase} phase.")
    return {"from_year": first_year, "to_year": current_season(db, league_id).year - 1,
            "seasons": count}


KINDS: dict[str, Runner] = {
    "sim_regular_season": _sim_regular_season,
    "sim_playoffs": _sim_playoffs,
    "advance_offseason": _advance_offseason,
    "finish_free_agency": _finish_free_agency,
    "finish_draft": _finish_draft,
    "sim_seasons": _sim_seasons,
}

LABELS = {  # what the progress bar says before the first step is done
    "sim_regular_season": "Simulating the season",
    "sim_playoffs": "Simulating the playoffs",
    "advance_offseason": "Running the offseason",
    "finish_free_agency": "Playing free agency",
    "finish_draft": "Finishing the draft",
    "sim_seasons": "Simming ahead",
}


def _season_steps(db: Session, season: Season) -> int:
    """Steps from where `season` is to the next preseason (weeks, playoff rounds, the
    offseason, market days, the draft)."""
    weeks = season_service.season_weeks(db, season.id)
    rounds = playoffs.round_count(db, season)
    if season.phase in ("preseason", "regular_season"):
        return max(0, weeks - season.current_week + 1) + rounds + 1 + MARKET_DAYS + 1
    if season.phase == "playoffs":
        return playoffs.rounds_left(db, season) + 1 + MARKET_DAYS + 1
    if season.phase == "offseason":
        return 1 + MARKET_DAYS + 1
    if season.phase == "free_agency":
        return MARKET_DAYS - (season.free_agency_day or 1) + 1 + 1
    return 1  # the draft


def _total(db: Session, season: Season, kind: str, params: dict | None = None) -> int:
    """How many steps the job will take (for the progress bar)."""
    if kind == "sim_seasons":
        weeks = season_service.season_weeks(db, season.id)
        full = weeks + playoffs.round_count(db, season) + 1 + MARKET_DAYS + 1
        return _season_steps(db, season) + full * ((params or {})["seasons"] - 1)
    if kind == "sim_regular_season":
        return max(1, season_service.season_weeks(db, season.id) - season.current_week + 1)
    if kind == "sim_playoffs":
        return max(1, playoffs.rounds_left(db, season))
    if kind == "finish_free_agency":
        return max(1, MARKET_DAYS - (season.free_agency_day or 1) + 1)
    return 1


MAX_SEASONS_AHEAD = 10


def enqueue(db: Session, league: League, kind: str, params: dict | None = None,
            team_id: int | None = None) -> Job:
    """Queue a job for the league (committed). 409 if one is already queued or running.
    `team_id`: the requester's team, whose games and signings the result singles out."""
    if kind not in KINDS:
        raise RosterError(f"Unknown job: {kind}", 422)
    if kind == "advance_offseason":
        from app.services.careers import settle_before_offseason  # (it builds on seasons)

        settle_before_offseason(db, league, autopilot=False)  # (refused: someone's fired)
    if kind == "sim_seasons":
        seasons = (params or {}).get("seasons")
        if not isinstance(seasons, int) or not 1 <= seasons <= MAX_SEASONS_AHEAD:
            raise RosterError(f"Sim ahead 1 to {MAX_SEASONS_AHEAD} seasons.", 422)
        if len(human_team_ids(db, league.id)) > 1:
            raise RosterError("Sim ahead is for leagues you play alone: with other managers, "
                              "the season moves a step at a time.")
        params = {"seasons": seasons}
    else:
        params = {"team_id": team_id} if team_id is not None else None
    if season_service.active_job(db, league.id) is not None:
        raise RosterError("A simulation is already running in this league.")
    season = current_season(db, league.id)
    if season is None:
        raise RosterError("The league has no season.", 404)
    job = Job(league_id=league.id, kind=kind, params=params,
              total=_total(db, season, kind, params), label=LABELS[kind])
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
        result = KINDS[job.kind](db, season, step, job.params or {})
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
