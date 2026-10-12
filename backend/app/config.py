from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/dynasty_football"
    # The web app's origins: browsers' changes from anywhere else are refused (api/access).
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Session cookies only over HTTPS (on wherever the site is served over HTTPS).
    cookie_secure: bool = False
    max_leagues: int = 10  # per account
    # The local account that `python -m app.seed` gives the league to (dev and e2e).
    dev_user_email: str | None = None
    dev_user_password: str | None = None
    seed: int = 2026
    # Background jobs: run them inside the request (tests), and/or run a worker thread in
    # the API process (development and e2e; production runs `python -m app.worker`).
    jobs_inline: bool = False
    worker_embedded: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
