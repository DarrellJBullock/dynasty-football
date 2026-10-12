# The game server: the API (default command) and the job worker (`python -m app.worker`).
# Build from backend/:  docker build -t dynasty-api --build-arg RELEASE=$(git rev-parse HEAD) .
# Before a new version starts: `alembic upgrade head` (Render runs it as the pre-deploy step).

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install .
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --create-home --uid 10001 dynasty
USER dynasty
ARG RELEASE=""
ENV RELEASE=$RELEASE PORT=8000 LOG_FORMAT=json
EXPOSE 8000
# Behind the host's load balancer and the web app, which pass on the browser's address.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
