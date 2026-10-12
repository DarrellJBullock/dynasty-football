from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app.api import (
    auth,
    coach,
    depth_chart,
    franchise,
    history,
    jobs,
    leagues,
    playbook,
    players,
    roster_import,
    season,
    stats,
    teams,
    trades,
)
from app.api.access import owned_league, same_site
from app.api.locks import league_unlocked
from app.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    stop = None
    if get_settings().worker_embedded:
        from app.worker import start_thread

        stop = start_thread()
    yield
    if stop is not None:
        stop.set()


def create_app() -> FastAPI:
    app = FastAPI(title="Dynasty Football: Next Gen API", version="0.1.0", lifespan=lifespan)
    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # The browser reaches the API through the web app (same origin, so no CORS). Every
    # route but these needs a signed-in user and only touches their own leagues
    # (api/access.py), and changes to a league wait while a background job simulates it
    # (api/locks.py).
    api.include_router(auth.router, dependencies=[Depends(same_site)])
    locked = [Depends(same_site), Depends(owned_league), Depends(league_unlocked)]
    for module in (franchise, leagues, teams, depth_chart, roster_import, players, season,
                   stats, trades, history, playbook, coach):
        api.include_router(module.router, dependencies=locked)
    api.include_router(franchise.franchises_router, dependencies=locked)
    api.include_router(jobs.router, dependencies=[Depends(same_site), Depends(owned_league)])
    app.include_router(api)
    return app


app = create_app()
