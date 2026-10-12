"""Logs, request ids and error reports.

- Every request gets an id: the caller's `X-Request-ID` (the web app passes one along)
  or a new one. It's sent back in the response, and every log line written while
  handling the request carries it.
- `LOG_FORMAT=json` writes one JSON object a line (deployed environments), with the
  request id, route, user id (never an email), status and duration of each request.
- Errors go to Sentry when `SENTRY_DSN` is set, tagged with the environment and release,
  with cookies, auth headers and passwords scrubbed.
"""

import contextvars
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request

from app.config import get_settings

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
log = logging.getLogger("app.request")

# Standard LogRecord attributes: anything else passed in `extra` goes into the JSON.
_RECORD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if rid := request_id.get():
            entry["request_id"] = rid
        entry.update({k: v for k, v in vars(record).items() if k not in _RECORD})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    """Root logging for the API or the worker, as LOG_FORMAT says."""
    handler = logging.StreamHandler()
    if get_settings().log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


SCRUBBED = "[scrubbed]"
_SECRET_KEYS = re.compile(r"password|token|secret|cookie|authorization", re.IGNORECASE)


def scrub(event: dict, _hint: dict | None = None) -> dict:
    """Sentry `before_send`: drop cookies, auth headers, and anything password-like."""
    request = event.get("request") or {}
    request.pop("cookies", None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if _SECRET_KEYS.search(key):
            headers[key] = SCRUBBED
    data = request.get("data")
    if isinstance(data, dict):
        for key in list(data):
            if _SECRET_KEYS.search(key):
                data[key] = SCRUBBED
    elif data is not None:
        request["data"] = SCRUBBED  # (a body we can't inspect)
    user = event.get("user") or {}
    for key in ("email", "ip_address", "username"):
        user.pop(key, None)
    return event


def init_sentry(component: str) -> bool:
    """Send errors to Sentry if a DSN is configured. Returns whether it's on."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment,
                    release=settings.release, send_default_pii=False, before_send=scrub,
                    traces_sample_rate=0.0)
    sentry_sdk.set_tag("component", component)
    return True


def _route_template(request: Request) -> str:
    """The matched route's path with its parameters ("/api/players/{player_id}"). An
    included router's routes only know their path below its prefix, so the prefix is
    whatever the URL has in front of the route's part."""
    route = request.scope.get("route")
    path = request.url.path
    if route is None:
        return path
    try:
        rendered = route.path_format.format(**request.path_params)
    except (AttributeError, KeyError, ValueError):
        return path
    prefix = path[: len(path) - len(rendered)] if path.endswith(rendered) else ""
    return prefix + route.path


def add_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        given = request.headers.get("x-request-id", "")
        rid = given if REQUEST_ID.match(given) else uuid.uuid4().hex
        token = request_id.set(rid)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            template = _route_template(request)
            log.info("%s %s %s", request.method, request.url.path, status, extra={
                "method": request.method, "route": template,
                "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "user_id": getattr(request.state, "user_id", None)})
            request_id.reset(token)
