# Dynasty Football: Next Gen

[![CI](https://github.com/DarrellJBullock/dynasty-football/actions/workflows/ci.yml/badge.svg)](https://github.com/DarrellJBullock/dynasty-football/actions/workflows/ci.yml)

A premium web-based American football franchise simulation with fictional teams and players.

**Stack:** Next.js 16 · React 19 · TypeScript · Tailwind CSS v4 · Three.js / React Three Fiber ·
Python FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 17

## Quick start (macOS)

Prerequisites: Node 22+, Python 3.12+, Homebrew.

```bash
brew install postgresql@17 && brew services start postgresql@17
make setup          # deps, databases, migrations, sample league
make dev-backend    # terminal 1 → http://localhost:8000/docs
make dev-frontend   # terminal 2 → http://localhost:3000
```

No Homebrew Postgres? `docker compose up -d db` and set `DATABASE_URL` in `backend/.env`
(see `docker-compose.yml`).

## Common commands

| Command | Does |
|---|---|
| `make test` | All tests (backend on PostgreSQL + frontend) |
| `make e2e` | End-to-end tests in a real browser (run `make e2e-setup` once first) |
| `make lint` | ruff, eslint, TypeScript |
| `make reseed` | Regenerate the sample league |
| `make help` | Everything else |

## Docs

- [GAME_DESIGN.md](GAME_DESIGN.md) — game rules and vision
- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, data model, API
- [ROADMAP.md](ROADMAP.md) — milestones
- [CLAUDE.md](CLAUDE.md) — conventions for contributors and Claude Code
