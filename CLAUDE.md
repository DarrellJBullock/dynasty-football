# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## Project

**Dynasty Football: Next Gen** — a web-based American football franchise simulation.
Read `GAME_DESIGN.md` (what we're building), `ARCHITECTURE.md` (how it fits together),
and `ROADMAP.md` (what's next) before starting a feature.

All teams, players, colleges, and leagues are **fictional**. Never add real NFL/NCAA
team names, logos, or real player names to seed data, fixtures, or tests.

## Layout

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (Python 3.12+, developed on 3.14)
  app/domain/     pure game rules (positions, ratings, contracts) — no DB, no HTTP
  app/services/   game logic using the DB (roster rules, standings, dashboard)
  app/api/        thin FastAPI routers; translate RosterError -> HTTP
  app/models.py   ORM models (schema source of truth for Alembic autogenerate)
  app/schemas.py  Pydantic request/response models
  app/seed/       deterministic fictional league generator (`python -m app.seed`)
  app/roster_import/  CSV/XLSX/JSON readers, row validation, templates (no DB)
  alembic/        migrations
  tests/          pytest
frontend/   Next.js 16 (App Router, Cache Components) + React 19 + Tailwind v4 + R3F
  src/app/        routes: / (dashboard), /roster, /depth-chart, /league
  src/components/ UI by feature (dashboard, roster, league, field, ui, shell)
  src/lib/        api client, types (mirror of schemas.py), pure helpers
```

## Commands (run from repo root)

```
make setup            # first time: venv, npm install, DBs, migrate, seed
make dev-backend      # API on :8000 (OpenAPI docs at /docs)
make dev-frontend     # web on :3000
make test             # backend (PostgreSQL) + frontend tests
make test-backend-fast  # backend on in-memory SQLite, no services needed
make lint             # ruff + eslint + tsc
make reseed           # wipe and regenerate the sample league
```

PostgreSQL is Homebrew `postgresql@17` (keg-only; the Makefile finds its binaries).

## Conventions

- **Layering:** `domain` must not import from `models`/`services`/`api`. Services hold
  rules that need the DB. Routes stay thin: load → call service → serialize.
- **Schema changes:** edit `app/models.py`, then
  `cd backend && .venv/bin/alembic revision --autogenerate -m "..."`, review the file,
  `make migrate`. `alembic check` must report no pending operations.
- **API changes:** update `app/schemas.py` *and* `frontend/src/lib/types.ts` together.
- **Ratings:** the 24 attributes live in `app/domain/ratings.py::ATTRIBUTES`; the
  `player_ratings` columns and `frontend/src/lib/attributes.ts` must match it.
  `Player.overall` is a cached value — recompute it whenever ratings or position change.
- **Determinism:** generators and (future) simulation take an explicit seed /
  `random.Random`; never use the global `random` module.
- **Tests:** every backend rule gets a pytest; every interactive frontend flow gets a
  Testing Library test with `@/lib/api` mocked. Keep both suites green.
- Python: ruff (line length 100). TS: eslint via `eslint-config-next`.
- **CI** (`.github/workflows/ci.yml`) runs on every PR and push to `main`: backend lint,
  migrations on an empty Postgres + `alembic check`, seed, pytest on Postgres and SQLite;
  frontend lint, typecheck, Vitest, and production build. Keep it green.

## Gotchas

- **Next.js 16 differs from older versions.** Read `frontend/node_modules/next/dist/docs/`
  before using an unfamiliar API. Notably:
  - `cacheComponents` is on: uncached data reads must sit inside `<Suspense>` (see
    `src/app/page.tsx`); `params`/`searchParams` are Promises.
  - The React lint rule forbids building JSX inside `try/catch`; use `attempt()` from
    `src/lib/api.ts` and render the error outside.
  - `LayoutProps`/`PageProps` types come from `next typegen` (run by `npm run typecheck`).
- **Three.js** components must be client-only: load via `next/dynamic` with
  `ssr: false` from a client component (see `components/field/FieldPreviewLoader.tsx`).
  Mock them in jsdom tests.
- **SQLAlchemy 2** does not cascade objects into the session through backrefs: append
  children through the parent relationship (`player.contracts.append(...)`).
- **Test isolation:** each test runs in a rolled-back SAVEPOINT. The SQLite engine in
  `tests/conftest.py` needs the pysqlite transaction workaround — keep it.
- **Team ratings need the depth chart:** `team_detail()` takes the team's saved
  overrides (`load_overrides`). Never compute a lineup from the raw roster; use
  `team_lineup()` / `domain.depth_chart`.
- **Next dev server** can serve a stale server render of a client component edited
  mid-session (shows as a hydration mismatch). Restart `make dev-frontend` to clear it.
- Single franchise for now: `current_franchise()` returns the earliest `franchises` row.
