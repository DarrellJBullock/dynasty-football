from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import franchise, leagues, players, roster_import, teams
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Dynasty Football: Next Gen API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (franchise, leagues, teams, roster_import, players):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
