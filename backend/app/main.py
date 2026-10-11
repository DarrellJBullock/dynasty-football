from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    coach,
    depth_chart,
    franchise,
    history,
    leagues,
    playbook,
    players,
    roster_import,
    season,
    stats,
    teams,
    trades,
)
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Dynasty Football: Next Gen API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],  # download filenames for exports
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (franchise, leagues, teams, depth_chart, roster_import, players, season,
                   stats, trades, history, playbook, coach):
        api.include_router(module.router)
    api.include_router(franchise.franchises_router)
    app.include_router(api)
    return app


app = create_app()
