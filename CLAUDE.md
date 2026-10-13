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
  app/worker.py   background job worker (`python -m app.worker`; long sims, services/jobs.py)
  alembic/        migrations
  tests/          pytest
unity/      Unity 6 project: the Unity viewer's WebGL renderer (C#; docs/unity.md)
frontend/   Next.js 16 (App Router, Cache Components) + React 19 + Tailwind v4 + R3F
  src/app/(app)/  the game (with the sidebar): / (dashboard), /roster, /depth-chart,
                  /schedule, /games/[id], /games/[id]/watch (3D), /games/[id]/coach,
                  /games/[id]/live (head-to-head) and
                  /coach (Coach Mode), /playoffs, /contracts, /free-agency, /draft,
                  /trades, /history, /stats, /players/[id], /league, /members,
                  /league-log, /leagues,
                  /leagues/new, /account
  src/app/(auth)/ /signin, /signup, /join (invite links) (no sidebar; a second root layout)
  src/app/(share)/ /share/[token]/… a league's read-only public link (no account; a third
                  root layout): standings, schedule, games, watch, playoffs, stats, history
  src/proxy.ts    sends visitors without a session cookie to /signin
  src/components/ UI by feature (dashboard, roster, league, field, watch, coach, ui, shell)
  src/lib/        api client, types (mirror of schemas.py), pure helpers
```

## Commands (run from repo root)

```
make setup            # first time: venv, npm install, DBs, migrate, seed
make dev-backend      # API on :8000 (OpenAPI docs at /docs), with a job worker thread
make worker           # a background job worker on its own
make dev-frontend     # web on :3000
make test             # backend (PostgreSQL) + frontend tests
make test-backend-fast  # backend on in-memory SQLite, no services needed
make e2e-setup        # once: e2e database + Playwright Chromium
make e2e              # Playwright: real browser, own DB and ports (8001/3001)
make lint             # ruff + eslint + tsc
make reseed           # wipe and regenerate the sample league
make perf             # time every API read on a league with seasons played
make parity           # 20 seasons in memory: records' spread, champions, streaks
make unity-test       # Unity's edit-mode tests (needs Unity installed)
make unity-build      # the Unity viewer's WebGL build into frontend/public/unity
scripts/setup-unity-runner.sh  # once, on the Unity Mac: the self-hosted runner (docs/unity.md)
scripts/smoke-test-images.sh API_IMAGE WEB_IMAGE  # (CI) run the built images together
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
  Game seeds come from database ids, which differ between e2e runs, so never assume what a
  given play is (play 2 can be a pre-snap foul, a starter can get hurt): find the play you
  need from the API, or assert what holds for any play.
- Python: ruff (line length 100). TS: eslint via `eslint-config-next`.
- **CI** (`.github/workflows/ci.yml`) runs on every PR and push to `main`: backend lint,
  migrations on an empty Postgres + `alembic check`, seed, pytest on Postgres (and on
  SQLite as a parallel job);
  frontend lint, typecheck, Vitest, and production build. Keep it green. The Unity build
  is its own workflow (`unity.yml`) on a self-hosted Mac runner, never a CI dependency.

## Gotchas

- **Next.js 16 differs from older versions.** Read `frontend/node_modules/next/dist/docs/`
  before using an unfamiliar API. Notably:
  - `cacheComponents` is on: uncached data reads must sit inside `<Suspense>` (see
    `src/app/(app)/page.tsx`); `params`/`searchParams` are Promises.
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
- **Don't `redirect()` to a destination that depends on game state** (e.g. "the next
  game"): the client router remembers the redirect and keeps following it after the state
  changes. Render the destination on the route instead (see `src/app/(app)/coach/page.tsx`).
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
- **Accounts and members:** every API route but `/api/health`, `/api/ready` and
  `/api/auth/*` needs a session. A league's members (`league_members`: commissioners and
  managers) see it; `leagues.user_id` is only its creator. `api/access.py` finds the league
  from a route's path ids (`league_of`: `league_id`, `season_id`, `team_id`, `player_id`,
  `game_id`, `franchise_id`, `job_id`) and answers 404 to non-members. A new route keyed by
  another id needs a case there; `test_accounts.py` walks every route and fails otherwise.
  Routes without ids must scope their queries to the user themselves. **Every change route
  needs a rule in `access.WRITES`** (commissioner, team, game, …); `test_members.py` fails
  on one without. Give a league to a user with `members.give_league` (seed, tests, perf).
- **The browser calls `/api` on the web app's own origin**, which `src/proxy.ts` passes on
  to the game server at request time (`lib/gameServer.ts`: `API_URL`, or `API_HOSTPORT`
  on Render), so the session cookie goes along and one build serves every environment;
  server components call it directly and forward the visitor's cookie (`lib/api.ts`).
  Never call the game server's URL from client code, and don't put the API address in
  `next.config.ts` (it's baked in at build time). A 401 in `attempt()` redirects to
  `/signin`. New public pages go in `PUBLIC` in `proxy.ts`.
- **Deployment** (`docs/deploy.md`): `render.yaml`, `backend/Dockerfile`,
  `frontend/Dockerfile`, `.github/workflows/deploy.yml`. Migrations run before a new API
  starts while the old one still serves, so keep each migration compatible with the
  previous release. New settings go in `app/config.py` and, if deployed, `render.yaml`.
- **Logging:** use `logging.getLogger("app.…")` with `extra={...}` for fields; never log
  emails, passwords or tokens (Sentry events are scrubbed by `observability.scrub`).
- **Tests sign in:** the backend's `client` fixture is signed in as the sample league's
  owner (`anonymous` isn't); every e2e test starts signed in as `E2E_USER`
  (`e2e/support/fixtures.ts`), which the reseed recreates.
- **Active franchise** = the user's most recent `franchises.activated_at`
  (`current_franchise(db, user)`). Every page reads `/api/franchise`, so never hard-code a
  league or team id. A franchise is one member's team (`franchises.user_id`; one per
  member and per team). **There's no "the franchise" of a league:** services take the
  acting member's `team_id` (`members.user_team_id`), and AI decisions skip every team a
  member runs (`members.human_team_ids`).
- **League deletion** deletes child rows explicitly (`services/leagues.delete_league`)
  because SQLite tests don't enforce `ON DELETE CASCADE`. Add new league-owned tables there.
- **Coached games replay from the user's calls** (`app/sim/coaching.py`): an engine change
  that alters the order of random draws changes how an in-progress coached game replays.
  Bump `SIM_VERSION` with such changes, and re-pin `NEUTRAL_GAME` in
  `tests/test_game_plans.py` (the play-log hash of a neutral-plan game).
- **Fatigue** (`app/sim/fatigue.py`): who's on the field comes from `fatigue.take`
  (healthy, not resting, as tired copies). In the engine, never pick on-field players with
  `team.at` directly; the in-game energy lives on the `SimTeam` and resets in
  `start_game`. Fatigue makes no random draws.
- **The Unity viewer** (`docs/unity.md`) only draws: the page's choreographer, clock,
  director and camera rig (`field/cameraFollow.ts`) drive it. `TimelineSampler.cs` and `Poses.cs`
  port `timeline.ts` and `poses.ts`, and `Athlete.cs` builds `PlayerFigure.tsx`'s figure;
  after changing any of them (or the choreographer), rewrite the shared fixtures
  (`UPDATE_UNITY_FIXTURES=1`) and run `make unity-test`. Its canvas needs an `id` (Unity's
  runtime looks it up). Without a build in `frontend/public/unity/` the Renderer switch
  disables Unity and `e2e/unity.spec.ts` skips. The page keeps one Unity (`leaseUnity`);
  viewers borrow it rather than start their own.
- **Sound** (`lib/sound/`, docs/design/sound.md) is the page's, for both renderers: the
  cues are pure (`cues.ts`) and fired by the viewer's onTick through `useGameSound`. No
  audio files: everything is synthesized (`engine.ts`). Browsers start audio only after a
  click or key, so turning sound on must happen in a click handler.
- **Commentary** (`lib/commentary.ts`) is written from play events, deterministically
  (phrasings picked from the game and play numbers), and must stay pronoun-neutral; a
  test checks every phrasing.
- **Penalties** (`app/sim/penalties.py`): a play whose result type is `"penalty"` was wiped
  out and counts only the foul in stats; a personal foul keeps the play's own type (the
  play stands) and adds a penalty event. Add a foul in `FOULS`, `NAMES`,
  `Tuning.penalty_rates` and the frontend's `src/lib/penalties.ts` together.
- **Long sims are background jobs** (`services/jobs.py`): while one is queued or running,
  every non-GET route under a league is refused with 409 by `api/locks.py` (the league
  comes from `access.league_of`, as for ownership). Job runners
  commit after each step, so a sim service they call must leave the league consistent
  between steps (see `season.simulate`'s `on_step`).
- **Game plans** (`sim/gameplan.py`): the AI picks named plays and calls through the
  team's plan. A neutral plan (the whole book, every tendency 0) must stay draw-for-draw
  identical to the AI before plans (`test_game_plans.py` pins a game's log): apply a
  tendency only when its level isn't 0, and only fall back when a pick finds nothing.
- **Head-to-head games** (`sim/coaching.replay_both`) script both sides: before each snap
  both coaches are asked, and `NeedCalls` names every side still to call, so neither sees
  the other's call first; kicking decisions and audibles stop for one side (`NeedCall.side`).
  Both sides on autopilot is the AI's game, draw for draw. A live game (`services/live.py`,
  `LiveGame`) keeps both sides' calls and replays them on every read; nothing may reveal one
  side's calls to the other (`live.state` shows only the viewer's situation). The week's sim
  finishes an unfinished one with the AI (`finish_with_ai`), and `turns.tick` runs call clocks.
  `CoachView` takes `actions` (call/auto/load) so `LiveView` reuses the call screen.
- **Audibles** are decided at the line inside a snap (`engine.at_the_line`): the answer is
  stored on that snap's recorded call (`CoachCall.audible`), not as a new call, and the look
  draws from its own `random.Random(f"look:{seed}:{n}:{role}")`, never the game's stream.
- **The season together** (`services/turns.py`): in a league where more than one member
  runs a team, managers check in (`league_members.ready_for` holds the `step_key` they're
  ready for, so advancing resets everyone), the commissioner advances one step
  (`turns.advance`), and the worker's minute (`turns.tick`) runs out draft clocks and the
  daily advance. The draft clock only runs with several managers (`draft._clocked`); a
  single-player league behaves as before. Sim ahead is refused with several managers.
- **Trades between managers** (`services/trade_offers.py`): a trade with another
  member's team is a `TradeOffer` they answer (accept, reject, counter); AI teams still
  answer at once (`trades.propose` refuses a member's team). Offers settle lazily
  (`settle`: expiry, offers whose players or picks moved, the end of the veto window) on
  every read and answer, and on the worker's tick. A trade's `team_id` is the proposer:
  show it from the viewer's side (`trades._trade_out(trade, viewer)`).
- **The League log** (`services/league_log.py`): every edit to a player or team and every
  commissioner action (vetoes, settings, member roles and removals) is recorded with
  `league_log.record` in the same transaction, with `changes` from `league_log.diff`. A new
  commissioner action records there too (add its action to `ACTIONS` and the frontend's
  `LeagueLogAction`). Editing players (ratings, bio, adding, importing, moving, contracts) is
  the commissioner's; a manager may only change their own player's jersey number.
- **Owners and fans** (`services/owners.py`, `domain/owners.py`): owners are made once per
  league (`ensure_owners`, with `random.Random(f"owners:{league.id}")`; a new league at
  creation, an older one when first needed), goals are set when the preseason opens (and
  before any sim), and every owner reviews the season when the champion is crowned
  (`review`; a rolled-back final calls `unreview`). Fan mood and goal status during a
  season are derived from the record, never stored week by week. JSON columns that
  are queried for `None` need `none_as_null=True` (see `OwnerSeason`).
- **AI trades** (`services/ai_trades.py`): after each regular week (and as the preseason
  opens) AI front offices may offer a member a trade (`TradeOffer.from_ai`: no veto window,
  a counter answered at once by `trades.propose`) and make a deadline deal among
  themselves; draws come from their own `ai-trades:` stream. A trade's `team_id` is whoever
  proposed it, an AI team included. Changing how AI teams build rosters or trade? Run
  `make parity`.
- **AI direction** (`services/direction.py`, `domain/direction.py`): each offseason (after
  development, before re-signing) every AI team decides to contend, sit in the middle or
  rebuild (`Team.direction`, with reasons), and re-signing, free agency and the draft follow
  it (`direction.of(team)`; the middle when there's none). Members' teams have none, except on
  autopilot. Directions use no random draws.
- **Job security** (`services/careers.py`): the owners' review fires general managers
  below `FIRE_LINE` when the league's `firing` rule allows (`careers.fires`). A fired member
  (`Franchise.fired_at`) must take another job (`take_job`) before the offseason begins
  (`settle_before_offseason`; on autopilot the owner keeps them). Moving a member changes
  `Franchise.team_id`: read the team by id, not through a loaded relationship. Careers are
  `GmStint` rows, made only when someone moves. The perf build turns firing off.
- **Money** (`services/money.py`, `domain/money.py`): a season's finances are derived from
  its games (each home gate from the fans' mood going into it) and the payrolls, never
  stored week by week; the owners' review keeps the season's (`OwnerSeason.finances`).
  Revenue scales with the league's salary cap. Money never limits spending (the cap and the
  staff budget do).
- **League rules** (`services/rules.py`, `League.roster_max`, `cap_growth_bp`,
  `playoff_seeds`, `season_weeks`) change only between seasons. **Never check a roster
  against `domain.positions.ROSTER_MAX`** (it's only the default): use the league's
  `roster_max`. Playoff seeding takes the league's choice (`playoffs._chosen`); a season's
  stored seeds decide its own rounds.
- **Rolling back a week** (`services/rollback.py`): `season.simulate` takes a
  `WeekSnapshot` before each week or round (the phase, the week, the games, every injury;
  one per league). `roll_back` undoes the week's games and everything they led to. Anything
  new that playing a week changes (and that rosters don't keep) must be saved in the
  snapshot or undone there, or a rollback leaves it behind. A week played as part of a
  longer sim replays with today's lineups (a long sim builds lineups once).
- **Reversing a trade** (`trades.reverse`): needs the trade's own contracts (the
  bonus-free one it gave each player, and the one before) and its dead money; a trade path
  that moves contracts differently must keep `reverse` working.
- **The read-only public link** (`services/sharing.py`, `api/public.py`): routes under
  `/api/public/{token}` need no session and only read; never return contracts there
  (`test_sharing.py` checks). The token is a key: `observability.loggable_path` hides it
  in request logs and Sentry. The views it reuses take a `site` (`lib/site.ts`): links go
  under `site.base`, and with `site.shared` there are no player pages, sim or coach
  controls. Public pages live under `PUBLIC_PREFIXES` in `proxy.ts`.
- **The league export** (`sharing.export_league`, docs/league-export.md) dumps each table's
  rows as stored; a new league-owned table goes there (or in the list of what's left out).
- **Legacy** (`services/legacy.py`, `domain/legacy.py`): the Hall of Fame votes once a
  year, at the end of `offseason.advance`, from careers summed out of the box scores.
  **Anywhere that issues a jersey number must skip the team's retired numbers**
  (`services/retired.py`: add them to the `taken` set given to `available_jersey`).
- **Staff** (`services/staff.py`, `domain/staff.py`): made once per league by
  `ensure_staff` with their own `random.Random(f"staff:{league.id}")`, never the
  generator's stream (a new league at creation; an older one the first time staff are
  read). Each staff member's season is written with the champion (`record_season`).
  What staff do never adds a draw: development scales `develop`'s change (`growth`,
  `decline`), scouting scales the projection error and the reports a class (per team:
  `draft.scouting`), and the trainer shortens layoffs after the game (`injuries.after_week`;
  the play log keeps the injury as it happened). Pass a team when a view depends on it.
  The coaching carousel (`services/carousel.py`) runs in `offseason.advance` (with its
  `autopilot` flag) and fills open jobs when the preseason opens (`draft._finish`); staff
  spend a staff budget (`leagues.staff_budget`), not the player cap. Facilities
  (`services/facilities.py`) add to the staff's effects by level (1 adds nothing): their
  upkeep and upgrades count in the staff payroll (`carousel.payroll`), and an upgrade
  arrives at the next offseason (`complete_upgrades`, before development).
- **Notifications** (`services/notifications.py`): call `notify` / `notify_team` /
  `notify_members` where something happens (a new kind goes in `KINDS`); pass a `key` when
  it must only happen once. Email is never sent in a request: a notification is marked
  `email="pending"` (for the kinds the member chose) and the worker's tick sends it. The
  sidebar's badge polls `/api/notifications/unread`; pages refresh when the tab comes back
  (`RefreshOnReturn`).
- **The franchise on autopilot:** the offseason, free agency and the draft take
  `autopilot=True` (sim ahead), which treats members' teams like AI teams. Anything new
  that skips the franchise for the user to decide needs the same flag.
- **Big JSON columns are deferred** (`Game.play_log`, `Season.offseason_log`): lists of
  games or seasons never load them. Reading one on many rows is a query each; add
  `undefer(...)` to that query. Keep new reads under budget: `make perf`, and CI fails a
  read over 600 ms or 80 queries.
- **Accessibility:** `e2e/a11y.spec.ts` runs axe (WCAG 2.2 AA) on every page and wants one
  `h1` each; add new pages to it. Don't put `aria-label` on a plain `div`/`span` (give it
  a role). Animations must respect `prefers-reduced-motion` (`lib/motion.ts`; CSS is
  handled globally).
- **Generator RNG order is load-bearing:** `build_league` must keep the default league
  byte-identical for a given seed (`tests/test_womens_leagues.py` pins its fingerprint).
  Append new random draws after existing ones; a women's league draws its own way.
