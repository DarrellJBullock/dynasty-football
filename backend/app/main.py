from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Response
from sqlalchemy.orm import Session

from app.api import (
    auth,
    coach,
    depth_chart,
    franchise,
    gameplans,
    history,
    jobs,
    leagues,
    legacy,
    members,
    notifications,
    playbook,
    players,
    public,
    roster_import,
    season,
    stats,
    teams,
    trades,
    turns,
)
from app.api.access import allowed, owned_league, same_site
from app.api.locks import league_unlocked
from app.config import get_settings
from app.db import get_db
from app.observability import add_request_logging, configure_logging, init_sentry
from app.services.health import readiness


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_sentry("api")
    stop = None
    if get_settings().worker_embedded:
        from app.worker import start_thread

        stop = start_thread()
    yield
    if stop is not None:
        stop.set()


def create_app() -> FastAPI:
    app = FastAPI(title="Dynasty Football: Next Gen API", version="0.1.0", lifespan=lifespan)
    add_request_logging(app)
    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @api.get("/ready", tags=["meta"])
    def ready(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
        """Readiness: the database answers and its schema is current (503 otherwise)."""
        status = readiness(db)
        if status["status"] != "ready":
            response.status_code = 503
        return status

    # The browser reaches the API through the web app (same origin, so no CORS). Every
    # route but these needs a signed-in user and only touches their own leagues
    # (api/access.py), and changes to a league wait while a background job simulates it
    # (api/locks.py).
    api.include_router(auth.router, dependencies=[Depends(same_site)])
    locked = [Depends(same_site), Depends(owned_league), Depends(allowed),
              Depends(league_unlocked)]
    for module in (franchise, leagues, teams, depth_chart, gameplans, roster_import, players,
                   season, stats, trades, history, playbook, coach, turns):
        api.include_router(module.router, dependencies=locked)
    api.include_router(franchise.franchises_router, dependencies=locked)
    api.include_router(members.router, dependencies=locked)
    api.include_router(trades.offers_router, dependencies=locked)
    api.include_router(notifications.router, dependencies=locked)
    api.include_router(legacy.router, dependencies=locked)
    # The read-only public link: no session; the link's token is the key.
    api.include_router(public.router, dependencies=[Depends(same_site)])
    api.include_router(members.invites_router, dependencies=[Depends(same_site)])
    api.include_router(jobs.router, dependencies=[Depends(same_site), Depends(owned_league),
                                                  Depends(allowed)])
    app.include_router(api)
    return app


app = create_app()
