from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/dynasty_football"
    # The web app's origins: browsers' changes from anywhere else are refused (api/access).
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Session cookies only over HTTPS (on wherever the site is served over HTTPS).
    cookie_secure: bool = False
    max_leagues: int = 10  # per account
    # Where this runs ("development", "staging", "production") and which build it is
    # (the commit, set by the image), for logs and error reports.
    environment: str = "development"
    release: str | None = None
    log_format: str = "text"  # "json" in deployed environments: one JSON object a line
    sentry_dsn: str | None = None  # error reports go to Sentry when set
    # The site's address, for links in emails (password reset).
    site_url: str = "http://localhost:3000"
    # Email: through SMTP when a host is set; otherwise written as files to `email_outbox`
    # (tests), or else logged (development).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "Dynasty Football <no-reply@example.test>"
    email_outbox: str | None = None
    # The local account that `python -m app.seed` gives the league to (dev and e2e).
    dev_user_email: str | None = None
    dev_user_password: str | None = None
    seed: int = 2026
    # Background jobs: run them inside the request (tests), and/or run a worker thread in
    # the API process (development and e2e; production runs `python -m app.worker`).
    jobs_inline: bool = False
    worker_embedded: bool = False

    @field_validator("database_url")
    @classmethod
    def _psycopg(cls, url: str) -> str:
        """Hosts hand out `postgres://` / `postgresql://` URLs; SQLAlchemy needs the driver."""
        for scheme in ("postgres://", "postgresql://"):
            if url.startswith(scheme):
                return "postgresql+psycopg://" + url[len(scheme):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
