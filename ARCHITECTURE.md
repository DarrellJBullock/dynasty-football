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
│   sim/       deterministic play-level game engine (pure)        │
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
| `app/domain` | nothing | Pure, unit-testable rules: positions, roster template, jersey ranges, attribute list, OVR weights, salary valuation, depth chart ordering and lineup selection. |
| `app/models.py` | `db` | ORM tables. Source of truth for migrations. |
| `app/services` | domain, models, schemas | Game logic needing the DB: roster mutations (`RosterError` on rule violations), team ratings/payroll, standings, dashboard assembly, ORM→schema serializers. |
| `app/api` | services | Thin routers. `roster_errors()` wraps a mutation in one transaction and maps `RosterError` → 4xx. |
| `app/seed` | domain, models | `build_league(session, spec, seed)` builds any league deterministically from a `LeagueCreate` spec; `generate_league` is the default spec. `league_template` makes editable specs from the fictional team pool. |
| `app/roster_import` | domain | File handling with no DB: `readers` (CSV/XLSX/JSON → raw rows), `rows` (normalize + validate each row), `writers` (rows → CSV/XLSX/JSON, shared by templates and exports), `templates`. `services/roster_import.py` adds roster-level checks (capacity, jerseys, payroll) and commits. |

### Data model

```
leagues 1─* conferences 1─* divisions 1─* teams 1─* players 1─1 player_ratings
   │                                          │          └──* contracts
   ├─* seasons 1─* games (home_team, away_team)
teams 1─* depth_chart_entries ─→ player   (saved slot orders only)
   └─* franchises ─→ team   (user's career save)
players.team_id NULL  = free agent
```

| Table | Key columns |
|---|---|
| `leagues` | name, abbreviation, salary_cap |
| `conferences`, `divisions` | name (+ abbreviation) |
| `teams` | city, nickname, abbreviation (unique per league), primary/secondary colour, stadium |
| `players` | league_id, team_id?, name, position, jersey (0–99), age, height_in, weight_lb, college, years_pro, **overall** (cached), potential, development_trait, injury_status, injury? (description), injury_weeks (games still to miss), retired_year? |
| `player_ratings` | player_id PK + 24 attribute columns (0–99) |
| `contracts` | player_id, team_id, start_year, years, salary, signing_bonus, is_active |
| `seasons` | league_id, year (unique per league), phase (preseason → regular_season → playoffs → offseason), current_week, champion_team_id?, offseason_log (what the rollover into this season did; JSON) |
| `playoff_seeds` | season_id, conference_id, team_id, seed, division_winner; fixed when the regular season ends |
| `games` | season_id, week, stage (regular \| playoff), playoff_round?, neutral_site, home/away team, scores (nullable), status, overtime, seed, sim_version, play_log (JSON/JSONB) |
| `player_game_stats` | game_id, player_id, team_id + one column per `sim.stats.PlayerLine` field |
| `team_game_stats` | game_id, team_id + one column per `sim.stats.TeamLine` field |
| `franchises` | name, league_id (unique — one career per league), team_id, activated_at (latest = active) |
| `depth_chart_entries` | team_id, slot (position), depth (1 = first string), player_id; unique per (team, slot, depth) and (team, slot, player) |

Design notes:
- Ratings are a separate 1:1 table so progression history / rating snapshots can be
  added later without widening `players`, and imports map columns 1:1.
- `players.overall` is denormalised for fast sorting; services recompute it on change.
- Standings are **derived** from final games, never stored.
- Depth charts store only customized slots; the effective chart is built on read
  (`domain/depth_chart.build_chart`), so new players, releases, and injuries never
  leave it inconsistent.

### API (v0)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/franchise` | Active franchise (league, team, season) |
| `GET /api/franchises` | Every franchise, most recently active first |
| `POST /api/franchises/{id}/activate` | Make a franchise active |
| `GET /api/leagues/template?conferences=&divisions=&teams_per_division=` | Editable league spec filled with fictional teams |
| `POST /api/leagues` | Create a league from a spec; creates and activates its franchise |
| `DELETE /api/leagues/{id}` | Delete a league and its contents (not the active one) |
| `PATCH /api/teams/{id}` | Edit team identity (city, nickname, abbreviation, colors, stadium) |
| `POST /api/seasons/{id}/simulate` `{until: next_week \| end_of_regular_season \| end_of_playoffs}` | Play a week (or playoff round) or the rest of a phase; persist scores, stats, play logs; seeds and schedules playoff rounds |
| `POST /api/seasons/{id}/advance` | After the champion: run the offseason (aging, development, retirements, contracts, rookies) and create the next season |
| `GET /api/leagues/{id}/playoffs` | Seeds (projected during the season), rounds and games, champion |
| `GET /api/leagues/{id}/schedule?week=` | One week (defaults to the next week to play) |
| `GET /api/games/{id}` | Line score, team & player stats, scoring summary, play-by-play, injuries |
| `GET /api/leagues/{id}/leaders?category=&limit=` | Season leaders: all categories (top 5) or one (up to 50) |
| `GET /api/leagues/{id}/team-stats` | Every team's season totals, offense and defense (allowed) |
| `GET /api/players/{id}/stats` | A player's season totals and game log |
| `GET /api/franchise/dashboard` | Everything the dashboard needs in one call |
| `GET /api/leagues`, `/api/leagues/{id}` | Leagues |
| `GET /api/leagues/{id}/teams` | All teams with ratings, payroll, cap space |
| `GET /api/leagues/{id}/standings` | Standings by division |
| `GET /api/leagues/{id}/free-agents?position=` | Free agent pool |
| `GET /api/teams/{id}`, `/api/teams/{id}/roster` | Team detail, roster |
| `POST /api/teams/{id}/players` | Create a custom player (409 if full / jersey taken / over cap) |
| `POST /api/teams/{id}/signings` | Sign a free agent |
| `GET /api/teams/{id}/depth-chart` | Effective chart: every slot's order, starters fielded, team ratings |
| `PUT /api/teams/{id}/depth-chart/{slot}` | Save a slot's order (may include cross-listed players) |
| `DELETE /api/teams/{id}/depth-chart/{slot}` | Reset one slot to OVR order |
| `DELETE /api/teams/{id}/depth-chart` | Reset every slot |
| `POST /api/teams/{id}/roster-import/preview` | Multipart `file` + `mode` (append/replace); validates without changing anything |
| `POST /api/teams/{id}/roster-import/commit` | Same file again + `skip_invalid`; all-or-nothing by default |
| `GET /api/roster-import/template.{csv,xlsx,json}` | Downloadable import template |
| `GET /api/teams/{id}/roster-export.{csv,xlsx,json}` | Roster in the import format (`HFD-roster-2026.csv`) |
| `GET /api/players/{id}` | Player with all 24 ratings |
| `PATCH /api/players/{id}` | Partial edit (bio, position, status, ratings); OVR recomputed |
| `POST /api/players/{id}/release` | Release to free agency |

Interactive docs: `http://localhost:8000/docs`.

## Frontend

- **Routing:** App Router. `/` dashboard, `/roster`, `/depth-chart`, `/league`,
  `/leagues` (saved franchises), `/leagues/new` (league builder), `/schedule?week=`,
  `/games/[id]`, `/playoffs`, `/stats?view=teams&category=`, `/players/[id]`. Every page reads the
  active franchise, so switching franchises re-points the whole app.
- **Data loading:** each page renders a static shell + `<Suspense>` skeleton; an async
  Server Component fetches from the API (`src/lib/api.ts`) and streams in. Errors are
  captured with `attempt()` and rendered by `ServerError` (offline / not seeded).
- **Interactivity:** the roster screen is a client component (`RosterManager`) seeded
  with server data, then mutating through the API and updating local state; the team
  header is re-fetched after each mutation.
- **Freshness:** mutations go straight to the API, so Next.js can't see them. Creating or
  switching the active franchise does a full page load (`lib/navigation.hardNavigate`),
  because the client router cache can otherwise reuse pages rendered for the previous
  franchise. Covered by `e2e/freshness.spec.ts`.
- **Season stats** are aggregated on read from `player_game_stats` / `team_game_stats`
  (`services/league_stats.py`) — no denormalized season tables to keep in sync. Box-score
  column groups are shared between the game and player pages (`lib/stats.ts`).
- **Season simulation** runs synchronously (a week ≈ 0.5 s, a season ≈ 8 s including
  writes). `services/season.py` snapshots every roster + depth chart once per run, seeds
  each game from (league, year, week, game id), and stores the box score rows and play
  log. Sim controls call `router.refresh()` afterwards so the current page re-renders.
- **Dialogs** render through a portal to `<body>`: a `.panel`'s `backdrop-filter` traps
  `position: fixed` descendants, which hid dialogs opened from inside panels.
- **Pure logic** (`lib/format.ts`, `lib/roster.ts`) is framework-free and unit-tested.
- **Design system:** tokens in `src/app/globals.css` (`@theme`): ink surface scale,
  chalk/mist text, gold accent, Barlow Condensed display font, `.panel`/`.btn`
  component classes. Team colours are injected as `--team-primary/secondary`.
- **Depth chart editor:** dnd-kit sortable lists (pointer, touch, keyboard) with arrow
  buttons as a fallback. Edits save immediately and optimistically; a failed save reverts
  and shows the error, and only the newest response is applied.
- **3D:** `components/field/FieldPreview.tsx` (R3F) is a decorative stadium scene,
  client-only via `next/dynamic({ ssr: false })`.

## Testing

| Suite | Tooling | What |
|---|---|---|
| Backend domain | pytest | OVR math, salary curve, jersey allocation, roster template |
| Backend generator | pytest | determinism, structure, roster composition, unique jerseys, cap compliance, schedule validity |
| Backend API | pytest + TestClient | every endpoint incl. 404/409/422 paths |
| Backend roster import | pytest | readers per format and bad files, header/position aliases, heights, rating fill/caps, errors vs warnings, preview/commit modes, skip-invalid, templates round-trip; export → re-import is lossless in every format |
| Backend leagues | pytest | spec validation, templates, creation (generated/empty rosters, custom identities, schedules for small leagues, determinism), franchise switching, team edits, protected delete |
| Simulation | pytest | determinism, score/clock/down invariants, box-score consistency, overtime rules, Coach seam, AI 4th-down/kneel calls, depth-chart lineups, calibration targets, rating sensitivity |
| Season | pytest | week/season simulation, persisted stats match scores, standings and dashboard follow results, reproducible seeds, injured QB benched, schedule/game endpoints, deleting played leagues |
| Season stats | pytest | leaders equal summed box scores (and "long" columns are maxima), released players keep their last team, player totals equal the game log, team totals reconcile with standings and league-wide (yards gained = allowed, turnovers = takeaways) |
| Playoffs | pytest | seed counts, pairing and reseeding, round names, each tiebreaker, division winners seeded first; full bracket to a neutral-site champion, offseason 409s, playoff games excluded from standings and stats, projected bracket, small one-conference leagues |
| Offseason | pytest | growth/decline/retirement curves, contract lengths; rollover creates the next season and schedule, ages players, retires and refills (full rosters, under the cap, one active contract each), determinism, retired players leave free agency, dashboard recap, a full season → next season through the API, multi-year stability |
| Injuries | pytest | contact and toughness odds, injury table ranges, injured players sit for the rest of the game, play outcomes unchanged before the first injury, determinism, status mapping, weekly countdown (hand-set statuses untouched), lineups skip the injured, dashboard report, game-page list, manual healing, offseason healing |
| Frontend lib | Vitest | formatting, filter/sort |
| Backend depth chart | pytest | ordering, lineup selection (injuries, no double starts), API save/reset/validation, release & position-change cleanup |
| Frontend components | Vitest + Testing Library | dashboard rendering; roster filter/sort/search, edit, release, sign, errors; depth chart reorder, revert on error, cross-listing, reset |

| End-to-end | Playwright (Chromium) | Real browser against a production build + real API/Postgres: navigation, roster edit/release/sign, depth chart mouse drag + keyboard reorder with screen-reader announcements, export → re-import via real download/upload, messy-file import, league create → switch → delete, team editing, cross-page data freshness |

Backend tests run on in-memory SQLite by default and on PostgreSQL with
`TEST_DATABASE_URL` (`make test`). The league is generated once per session; each test
runs in a rolled-back SAVEPOINT.

End-to-end tests (`frontend/e2e/`, `make e2e`) start their own API (port 8001) and
production Next.js build (port 3001, built into `.next-e2e/`) against the
`dynasty_football_e2e` database, reseeding it before every test, so they never touch dev
servers or dev data. CI runs them as a third job and uploads traces on failure.

## Future architecture (planned)

### Simulation engine (`backend/app/sim/`)

Design and calibration targets: [`docs/design/simulation-engine.md`](docs/design/simulation-engine.md).

- **Pure and deterministic:** `simulate_game(home, away, seed)` takes two `SimTeam`
  snapshots (built from rosters + depth charts by `build_sim_team`) and returns a
  `GameResult` with a play log. Same inputs → same game. No DB access in `app/sim/`.
- **Play-level:** each snap is resolved from the two calls (`playcalls.AICoach`; the
  `Coach` protocol is the Coach Mode seam) and the specific players' matchups
  (`resolve.py`). Probabilities are `sigmoid(base + k · rating_difference)`.
- **Events are the contract:** every play records semantic events (handoff, rush, pass,
  sack, tackle, penalty, kicks…). Play-by-play text (`text.py`) and box scores
  (`stats.py`) are derived from events only, and the 3D client will animate from them —
  the engine never computes player positions.
- **Calibration:** all constants live in `tuning.py`; `calibration.py` measures league
  output against targets, and `tests/test_sim_calibration.py` enforces them plus rating
  sensitivity (+5 OVR ≈ 70% wins). A full 272-game season simulates in ~2 s.

### 3D game client

- R3F scene graph: stadium, 22 rigged player models, ball, cameras.
- Animation driven by the engine timeline (playback, not client-side physics), so
  replays and Watch Mode are exact.
- State machines per player (stance → route/block/rush → tackle/celebrate).
- Camera rigs: broadcast sideline, all-22, end zone, follow-ball; replay scrubbing.

### Later concerns

Auth & multiple saves (franchise per user), league-wide export,
stats tables (game_player_stats), records, background jobs, deployment (containerised
API + Postgres; Next.js on a Node host).
