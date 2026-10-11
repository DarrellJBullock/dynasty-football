from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/dynasty_football"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    seed: int = 2026
    # Background jobs: run them inside the request (tests), and/or run a worker thread in
    # the API process (development and e2e; production runs `python -m app.worker`).
    jobs_inline: bool = False
    worker_embedded: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
