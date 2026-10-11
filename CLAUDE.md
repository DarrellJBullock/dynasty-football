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
  app/sim/        play-level game simulation engine (pure, deterministic)
  alembic/        migrations
  tests/          pytest
frontend/   Next.js 16 (App Router, Cache Components) + React 19 + Tailwind v4 + R3F
  src/app/        routes: / (dashboard), /roster, /depth-chart, /schedule, /games/[id],
                  /games/[id]/watch (3D), /games/[id]/coach and /coach (Coach Mode),
                  /playoffs, /contracts, /free-agency, /draft, /trades, /history,
                  /stats, /players/[id], /league, /leagues, /leagues/new
  src/components/ UI by feature (dashboard, roster, league, field, watch, coach, ui, shell)
  src/lib/        api client, types (mirror of schemas.py), pure helpers
```

## Commands (run from repo root)

```
make setup            # first time: venv, npm install, DBs, migrate, seed
make dev-backend      # API on :8000 (OpenAPI docs at /docs)
make dev-frontend     # web on :3000
make test             # backend (PostgreSQL) + frontend tests
make test-backend-fast  # backend on in-memory SQLite, no services needed
make e2e-setup        # once: e2e database + Playwright Chromium
make e2e              # Playwright: real browser, own DB and ports (8001/3001)
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
- **Determinism:** generators and the simulation take an explicit seed /
  `random.Random`; never use the global `random` module.
- **Simulation tuning:** change constants in `app/sim/tuning.py` (or `RATING_SPREAD`
  in `sim/teams.py`), never hard-code numbers in resolvers. Check with
  `python -m app.sim.calibration`; `tests/test_sim_calibration.py` must stay green. Stats
  and play-by-play must be derived from play events, never computed separately.
- **Tests:** every backend rule gets a pytest; every interactive frontend flow gets a
  Testing Library test with `@/lib/api` mocked; user-visible flows that cross pages or
  need a real browser (drag-and-drop, downloads/uploads, navigation) get a Playwright
  spec in `frontend/e2e/`. Keep all suites green.
- **E2E locators:** use roles and accessible names, scope `getByRole("alert")` to
  `getByRole("main")` (Next adds a route announcer with role="alert"), and pass
  `exact: true` when one name is a substring of another ("League" / "My Leagues").
  Next keeps up to 3 visited pages mounted but hidden (React `<Activity>`), so scope text
  locators to a visible region/role; page-wide `getByText` can match hidden pages.
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
- **Client hooks reading the URL** (`usePathname`, `useSearchParams`) in the layout must
  sit inside `<Suspense>`, or dynamic routes like `/games/[id]` can't prerender (see
  `shell/Sidebar.tsx`).
- **Stats columns mirror `sim.stats` dataclasses**; a test fails if they drift. Add a
  field to `PlayerLine`/`TeamLine` → add the column + a migration.
- **Dialogs must portal** to `document.body` (see `components/ui/Dialog.tsx`); any
  ancestor with `backdrop-filter` (every `.panel`) otherwise traps the fixed overlay.
- **After creating/switching a franchise use `hardNavigate("/")`**, not `router.push` —
  the client router cache can serve pages from the previous franchise.
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
- **Active franchise** = most recent `franchises.activated_at` (`current_franchise()`).
  Every page reads `/api/franchise`, so never hard-code a league or team id. One
  franchise per league (unique constraint).
- **League deletion** deletes child rows explicitly (`services/leagues.delete_league`)
  because SQLite tests don't enforce `ON DELETE CASCADE`. Add new league-owned tables there.
- **Coached games replay from the user's calls** (`app/sim/coaching.py`): an engine change
  that alters the order of random draws changes how an in-progress coached game replays.
  Bump `SIM_VERSION` with such changes.
- **Generator RNG order is load-bearing:** `build_league` must keep the default league
  byte-identical for a given seed. Append new random draws after existing ones.
