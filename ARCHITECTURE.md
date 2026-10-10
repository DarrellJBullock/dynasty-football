# Architecture

## Overview

```
┌──────────────────────────── Browser ────────────────────────────┐
│ Next.js 16 client: React 19, Tailwind v4, React Three Fiber     │
│   interactive islands (roster editor, dialogs, 3D field)        │
└──────────────┬───────────────────────────────▲──────────────────┘
               │ fetch (mutations, lazy data)  │ streamed HTML/RSC
┌──────────────▼───────────────────────────────┴──────────────────┐
│ Next.js server: Server Components fetch the API inside          │
│ <Suspense>; static shell is prerendered (Partial Prerendering)  │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP JSON  /api/*
┌──────────────▼──────────────────────────────────────────────────┐
│ FastAPI                                                         │
│   api/       routers (validation, HTTP errors)                  │
│   services/  roster rules, standings, dashboard, team ratings   │
│   domain/    pure rules: positions, ratings/OVR, contracts      │
│   seed/      deterministic fictional league generator           │
│   (future) sim/  deterministic play & game engine               │
└──────────────┬──────────────────────────────────────────────────┘
               │ SQLAlchemy 2 (psycopg 3)
┌──────────────▼──────────────────────────────────────────────────┐
│ PostgreSQL 17  — schema managed by Alembic                      │
└─────────────────────────────────────────────────────────────────┘
```

The browser talks to FastAPI directly for mutations (CORS allows `localhost:3000`);
Server Components call it server-side for initial page data.

## Backend

### Layers

| Layer | Depends on | Responsibility |
|---|---|---|
| `app/domain` | nothing | Pure, unit-testable rules: positions, roster template, jersey ranges, attribute list, OVR weights, salary valuation. |
| `app/models.py` | `db` | ORM tables. Source of truth for migrations. |
| `app/services` | domain, models, schemas | Game logic needing the DB: roster mutations (`RosterError` on rule violations), team ratings/payroll, standings, dashboard assembly, ORM→schema serializers. |
| `app/api` | services | Thin routers. `roster_errors()` wraps a mutation in one transaction and maps `RosterError` → 4xx. |
| `app/seed` | domain, models | `generate_league(session, seed)` builds the default league deterministically. |
| `app/roster_import` | domain | File handling with no DB: `readers` (CSV/XLSX/JSON → raw rows), `rows` (normalize + validate each row), `templates`. `services/roster_import.py` adds roster-level checks (capacity, jerseys, payroll) and commits. |

### Data model

```
leagues 1─* conferences 1─* divisions 1─* teams 1─* players 1─1 player_ratings
   │                                          │          └──* contracts
   ├─* seasons 1─* games (home_team, away_team)
   └─* franchises ─→ team   (user's career save)
players.team_id NULL  = free agent
```

| Table | Key columns |
|---|---|
| `leagues` | name, abbreviation, salary_cap |
| `conferences`, `divisions` | name (+ abbreviation) |
| `teams` | city, nickname, abbreviation (unique per league), primary/secondary colour, stadium |
| `players` | league_id, team_id?, name, position, jersey (0–99), age, height_in, weight_lb, college, years_pro, **overall** (cached), potential, development_trait, injury_status |
| `player_ratings` | player_id PK + 24 attribute columns (0–99) |
| `contracts` | player_id, team_id, start_year, years, salary, signing_bonus, is_active |
| `seasons` | league_id, year (unique per league), phase, current_week |
| `games` | season_id, week, home/away team, scores (nullable), status |
| `franchises` | name, league_id, team_id |

Design notes:
- Ratings are a separate 1:1 table so progression history / rating snapshots can be
  added later without widening `players`, and imports map columns 1:1.
- `players.overall` is denormalised for fast sorting; services recompute it on change.
- Standings are **derived** from final games, never stored.

### API (v0)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/franchise` | Active franchise (league, team, season) |
| `GET /api/franchise/dashboard` | Everything the dashboard needs in one call |
| `GET /api/leagues`, `/api/leagues/{id}` | Leagues |
| `GET /api/leagues/{id}/teams` | All teams with ratings, payroll, cap space |
| `GET /api/leagues/{id}/standings` | Standings by division |
| `GET /api/leagues/{id}/free-agents?position=` | Free agent pool |
| `GET /api/teams/{id}`, `/api/teams/{id}/roster` | Team detail, roster |
| `POST /api/teams/{id}/players` | Create a custom player (409 if full / jersey taken / over cap) |
| `POST /api/teams/{id}/signings` | Sign a free agent |
| `POST /api/teams/{id}/roster-import/preview` | Multipart `file` + `mode` (append/replace); validates without changing anything |
| `POST /api/teams/{id}/roster-import/commit` | Same file again + `skip_invalid`; all-or-nothing by default |
| `GET /api/roster-import/template.{csv,xlsx,json}` | Downloadable import template |
| `GET /api/players/{id}` | Player with all 24 ratings |
| `PATCH /api/players/{id}` | Partial edit (bio, position, status, ratings); OVR recomputed |
| `POST /api/players/{id}/release` | Release to free agency |

Interactive docs: `http://localhost:8000/docs`.

## Frontend

- **Routing:** App Router. `/` dashboard, `/roster`, `/league`.
- **Data loading:** each page renders a static shell + `<Suspense>` skeleton; an async
  Server Component fetches from the API (`src/lib/api.ts`) and streams in. Errors are
  captured with `attempt()` and rendered by `ServerError` (offline / not seeded).
- **Interactivity:** the roster screen is a client component (`RosterManager`) seeded
  with server data, then mutating through the API and updating local state; the team
  header is re-fetched after each mutation.
- **Pure logic** (`lib/format.ts`, `lib/roster.ts`) is framework-free and unit-tested.
- **Design system:** tokens in `src/app/globals.css` (`@theme`): ink surface scale,
  chalk/mist text, gold accent, Barlow Condensed display font, `.panel`/`.btn`
  component classes. Team colours are injected as `--team-primary/secondary`.
- **3D:** `components/field/FieldPreview.tsx` (R3F) is a decorative stadium scene,
  client-only via `next/dynamic({ ssr: false })`.

## Testing

| Suite | Tooling | What |
|---|---|---|
| Backend domain | pytest | OVR math, salary curve, jersey allocation, roster template |
| Backend generator | pytest | determinism, structure, roster composition, unique jerseys, cap compliance, schedule validity |
| Backend API | pytest + TestClient | every endpoint incl. 404/409/422 paths |
| Backend roster import | pytest | readers per format and bad files, header/position aliases, heights, rating fill/caps, errors vs warnings, preview/commit modes, skip-invalid, templates round-trip |
| Frontend lib | Vitest | formatting, filter/sort |
| Frontend components | Vitest + Testing Library | dashboard rendering; roster filter/sort/search, edit, release, sign, errors |

Backend tests run on in-memory SQLite by default and on PostgreSQL with
`TEST_DATABASE_URL` (`make test`). The league is generated once per session; each test
runs in a rolled-back SAVEPOINT.

## Future architecture (planned)

### Simulation engine (`backend/app/sim/`)

- Deterministic, seeded, pure Python first (port hot paths later if needed).
- `simulate_play(state, offense_call, defense_call, rng) -> PlayResult` where the
  result includes an **event timeline** (per-player positions/actions over time).
- `simulate_game` composes plays; Quick Sim persists box scores and player stats.
- Long jobs (season sims) run in a background worker; progress via polling/SSE.

### 3D game client

- R3F scene graph: stadium, 22 rigged player models, ball, cameras.
- Animation driven by the engine timeline (playback, not client-side physics), so
  replays and Watch Mode are exact.
- State machines per player (stance → route/block/rush → tackle/celebrate).
- Camera rigs: broadcast sideline, all-22, end zone, follow-ball; replay scrubbing.

### Later concerns

Auth & multiple saves (franchise per user), roster export,
stats tables (game_player_stats), records, background jobs, deployment (containerised
API + Postgres; Next.js on a Node host).
