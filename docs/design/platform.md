# Design: Platform (Milestone 7)

**Status:** Accepted 2026-10-11 (all §9 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Turn the game from something that runs on one developer's machine into something people
can sign up for and play. Each player gets an **account** with their own saved franchises,
long simulations run as **background jobs** with progress, the app **deploys** from CI to a
staging and a production environment with **monitoring**, and a **performance and
accessibility pass** sets budgets and keeps them in CI.

### Non-goals for Milestone 7

- Multiplayer: two people in one league, online play, trading between users. Each league
  stays one person's world. The data model shouldn't rule it out, but it isn't built.
- Payments, subscriptions, ads.
- Native mobile apps. The web app should work on a phone, but there's no store app.
- Simulation, gameplay or presentation changes. The game itself is the same game.

## 2. What exists

- **Saves, but no owners.** A league holds one franchise (a career save). `/leagues` lists
  every franchise and switches between them; the **active franchise** is simply the most
  recently activated one in the whole database (`services/dashboard.current_franchise`).
  Anyone who can reach the API can read and change everything.
- **About 70 API routes** keyed by league, season, team, player and game ids, with no
  check of who's asking. Mutations come straight from the browser to FastAPI (CORS allows
  `localhost:3000`); Server Components call the API server-side.
- **Synchronous sims.** Measured on the sample league (Postgres, this machine):

  | Request | Time |
  |---|---|
  | Sim one week | 0.5 s |
  | Sim the rest of the regular season | 8.1 s |
  | Sim the playoffs | 2.3 s |
  | Advance through the offseason | 2.5 s |
  | League history | 0.9 s |

  The browser waits on one HTTP request with a spinner and no progress. A hosted server
  with request timeouts, slower disks or several users at once would be worse.
- **Local only.** `make setup` builds a venv, installs npm packages and creates the
  databases. There are no Dockerfiles for the app (only an optional Postgres in
  `docker-compose.yml`), no hosting, no error reporting, no logs beyond the console.
- **CI** runs lint, migrations on an empty Postgres with `alembic check`, pytest on
  Postgres and SQLite, Vitest, the production build, and Playwright end-to-end tests.
- **Accessibility** is good in places: roles and accessible names throughout (the e2e
  tests depend on them), a keyboard-accessible depth chart with screen-reader
  announcements, HTML overlays over the 3D canvas, and the play-by-play as a text
  alternative to it. It has never been audited.

## 3. Accounts

- **Sign up and sign in with an email and a password**, handled by the FastAPI backend.
  Passwords are hashed with Argon2. Signing in creates a server-side **session** (a row in
  a `sessions` table) and sets an `HttpOnly`, `Secure`, `SameSite=Lax` cookie holding the
  session's random token; the table keeps only the token's SHA-256. Signing out deletes
  the row. (`Secure` is a setting, off for `http://localhost`.) Sessions last 30 days and are
  extended when they're used.
- **One origin.** The browser calls `/api/*` on the web app's own origin, and Next.js
  proxies it to FastAPI (a rewrite). The cookie is then first-party for both, CORS goes
  away, and Server Components forward the visitor's cookie when they call the API.
  Mutations also check the `Origin` header against the site, which together with
  `SameSite=Lax` stops cross-site request forgery.
- **Ownership.** `leagues.user_id` says whose league it is. Every resource reaches a
  league (a player through its league, a game through its season), so one router
  dependency (`api/access.py`) finds the league from any route's path ids, checks its
  owner, and returns 404 (not 403) for someone else's, so ids don't leak what exists.
  Routes without ids (the active franchise, the league list) scope their queries to the
  user. A test walks every
  route in the OpenAPI schema and checks that a second user gets a 404 from each one.
- **The active franchise is per user**: the user's most recently activated franchise.
  `current_franchise(db, user)` replaces today's global query.
- **Pages:** sign up, sign in, sign out (in the sidebar), and an account page (change
  password, which signs out other browsers; delete the account and everything in it,
  after the password). Signing in and up have their own root layout without the game's
  sidebar (route groups `(auth)` and `(app)`). A visitor without a session cookie is sent
  to sign in by `proxy.ts`, and back afterwards (`?next=`); a session the API turns away
  does the same through `attempt()`. A new account goes straight to building its first
  league.
- **Password reset** needs email delivery. It comes with deployment (§5), through a
  transactional email service; until then an admin command resets a password
  (`python -m app.accounts set-password EMAIL`, which asks for it and signs out
  everywhere).
- **Limits:** failed sign-ins are limited to 10 per email and 50 per address in 15
  minutes (then 429), counted in the API process (with several instances, each counts
  its own). Each user may keep
  up to 10 leagues (a setting), because each league with a few seasons is several MB.
- **Existing data:** the migration adds `users` and `sessions` and leaves
  `leagues.user_id` empty for existing leagues. The first account created on an install
  claims them, so a developer's current saves carry over.
- **Local development and tests:** `make setup` and `make reseed` create a local account
  (`DEV_USER_EMAIL` and `DEV_USER_PASSWORD` in `backend/.env`; `dev@example.test` in the
  example) owning the sample league. The e2e fixture signs
  in through the API and reuses the cookie (Playwright `storageState`). Backend tests get
  a signed-in client fixture. One e2e spec covers sign up, sign in, sign out, and that a
  second account can't see the first one's league.

## 4. Background jobs

- **A job queue in Postgres**, with no new infrastructure: a `jobs` table (kind, league,
  status `queued`/`running`/`done`/`failed`/`cancelled`, progress `n of m` with a label, a
  stop request, result, error, timestamps; the owning user arrives with accounts) and a
  **worker** process (`python -m app.worker`) that claims the oldest queued job with
  `SELECT … FOR UPDATE SKIP LOCKED`, runs it, and records progress as it goes. Several
  workers can run side by side.
- **What becomes a job:** anything that can take more than about a second. That means
  simming the rest of the regular season, the playoffs, advancing through the offseason,
  and finishing free agency or the draft. A single week, a free-agency day and a draft
  pick stay synchronous: they take half a second or less, and stepping through them
  should feel instant.
- **The API:** `POST /api/leagues/{id}/jobs` `{kind}` returns `202 Accepted` with the job.
  `GET /api/jobs/{id}` reports its status and progress, and its result once done: the same
  body the matching synchronous endpoint returns. `DELETE` asks it to stop after the
  current week (round, market day); the offseason and the draft run as one step. A long
  sim commits week by week, so a stopped or failed job leaves the league at a clean
  boundary, and since every game is seeded on its own, carrying on plays the same games.
  The synchronous endpoints still accept the long modes, for scripts and tests; the app
  uses jobs for them.
- **One job per league at a time** (a partial unique index). While a job is queued or
  running, the league's other changes return 409 ("a simulation is running"): one router
  dependency (`api/locks.py`) finds the league from any route's path ids. Reads still
  work, so the user can browse while it runs.
- **The UI:** the sim controls show a progress bar ("Week 9 of 17") with Stop, and the
  page refreshes when the job finishes. Leaving the page doesn't stop the job: every
  season carries its league's `active_job`, so the controls on any page pick it up again.
- **Determinism is unchanged.** A job runs the same service code with the same seeds as
  the synchronous request.
- **Locally,** `make dev-backend` runs a worker in a thread of the API
  (`WORKER_EMBEDDED=1`), as the e2e servers do; `make worker` runs one on its own.
  Backend tests run jobs inside the request, and drive the worker's claim-and-run loop
  directly; the e2e season test runs every kind of job through the real worker.
- **Recovery:** a job whose worker died (no heartbeat for a minute) is marked failed, and
  the league is unlocked.

## 5. Deployment

- **Containers.** Dockerfiles for the API and worker (one image, two commands) and for the
  web app (Next.js standalone output). Every PR builds them and smoke-tests them together
  against Postgres (`scripts/smoke-test-images.sh`); after CI passes on `main` they're
  pushed to GitHub's container registry, tagged with the commit. The web app reads the
  API's address at request time (`src/proxy.ts`, `API_URL` or `API_HOSTPORT`), so one
  image serves every environment.
- **Hosting:** **Render** (§9, decision 7): the web app (a web service), the API (a
  private service) and the worker (a background worker) run the images, with a managed
  Postgres, all defined in `render.yaml` as a project with `staging` and `production`
  environments. Same-origin `/api` makes the web app the only public service.
- **Environments:** **staging** deploys automatically from `main`. **Production** deploys
  the same images after a manual approval in GitHub Actions (required reviewers on the
  `production` environment). Each has its own database. The Deploy workflow
  (`.github/workflows/deploy.yml`) deploys through Render's API: the API, then the worker,
  then the web app, then checks `/api/ready`.
- **Migrations** run as a release step (Render's pre-deploy command, `alembic upgrade
  head`) before the new API starts.
  Migrations stay backward compatible for one release, so the old and new versions can
  run side by side during a deploy.
- **Secrets** (database URL, session secret, error-reporting and email keys) live in the
  host's secret store and GitHub environments, never in the repo.
- **Backups:** the managed database's daily backups plus point-in-time recovery, and a
  documented restore drill.
- **Setting it up needs you.** I can write all the configuration, but creating the hosting
  and error-reporting accounts, and connecting them to GitHub, is yours to do. The runbook
  is `docs/deploy.md`.
- **Password reset email:** "Forgot your password?" emails a one-time link, good for an
  hour (`password_resets` keeps only its token's SHA-256), sent through any email
  service's SMTP; the answer is the same whether or not the account exists, and an
  address gets at most 5 an hour. Locally the email is logged; the e2e tests read it from
  an outbox folder.

## 6. Monitoring

- **Health checks:** `/api/health` (the process is up) and `/api/ready` (the database
  answers, migrations are current). The host restarts what fails.
- **Structured logs:** JSON lines with a request id passed from the web app to the API
  and on into jobs, the route, the user id (never an email), status and duration.
- **Error tracking** with Sentry on the API, the worker and the web app (server and
  browser), with releases tagged by commit. Personal data is scrubbed.
- **Uptime:** a scheduled GitHub Actions workflow checks the sign-in page and
  `/api/ready` of each environment every 10 minutes (the shortest schedule Actions keeps
  reliably); GitHub emails when it fails. Sentry's uptime monitors can check every minute.
- **Job metrics** in the logs: each job's queued, started and finished lines (kind,
  status, progress, run time), the queued line carrying the request id that started it.

## 7. Performance

- **Budgets,** measured on the sample league with a few seasons played:
  - Every API read under 300 ms at the 95th percentile. Today, league history (0.9 s)
    misses it.
  - Sims as fast as today or faster: a regular season within 10 s, as a job.
  - Pages: Largest Contentful Paint under 2.5 s and layout shift under 0.1, on a mid-range
    laptop profile.
  - The Watch page's JavaScript loaded only there (three.js stays out of other pages).
- **Work done** (measured with `python -m app.perf` on three seasons played):

  | Read | Before | After |
  |---|---|---|
  | League history | 2,820 ms, 118 queries | 72 ms, 65 queries |
  | Playoffs | 768 ms | 17 ms |
  | League teams | 476 ms, 85 queries | 118 ms, 16 queries |
  | Dashboard | 437 ms | 31 ms |
  | Trades, standings, team stats | ~400 ms each | 95, 13, 24 ms |

  - The big one: every list of games loaded each game's play log (tens of KB), and
    every "current season" lookup loaded every season's offseason log. Both columns are
    now deferred, loaded only for the one game or season that reads them, and the
    season lookup takes one row.
  - League records were two scans of the league's stat lines per category; now one
    pass sums them all.
  - The teams list looks up dead money for all teams at once.
  - With reads this fast, caching past seasons isn't needed; it can come back if leagues
    grow far larger.
- **In CI:** the backend job builds two seasons and runs `app.perf measure` with a
  600 ms ceiling (the budget, with room for a slow runner) and 80 queries per read. Page
  budgets are checked in Playwright (`e2e/performance.spec.ts`) rather than Lighthouse
  CI: Lighthouse can't easily get past the sign-in, while Playwright measures LCP and
  layout shift on the production build already signed in, and checks that three.js stays
  off pages without a 3D view.

## 8. Accessibility

- **Target: WCAG 2.2 AA.**
- **Automated:** axe-core runs in Playwright on every page, in both the empty and played
  states, and fails on any serious or critical violation.
- **By hand:** keyboard-only and screen-reader (VoiceOver) passes through the main flows:
  sign in, roster, depth chart, sim a week, a game, the Watch page, Coach Mode, free
  agency, the draft. Fix focus order, focus after dialogs and navigation, skip links,
  heading structure, form labels and error messages, and colour contrast of the design
  tokens.
- **Done:** axe found and we fixed ARIA labels on plain elements (the 3D views and the
  score bug's pips are now labelled images), the score bug's team-colour contrast (text
  now picks dark or white by contrast ratio), a roster count's contrast, the player
  page's definition lists, and 24 px touch targets on the schedule. Every page has one
  `h1`; a "Skip to content" link leads past the sidebar; dialogs already trapped and
  returned focus. A keyboard-only Playwright test signs in, skips to the page and sims a
  week. The screen-reader (VoiceOver) pass still needs a person.
- **Motion:** with `prefers-reduced-motion`, the Watch page cuts without easing, turns
  off instant replays by default and doesn't wipe, and banners appear without animating.
  (`lib/motion.ts`; the 3D cameras also stop orbiting, Coach Mode's reel skips replays,
  and CSS animations finish at once.)
- **The 3D view** stays decorative to assistive technology: the play caption, score bug
  and play-by-play carry the same information as text, and the scene's controls are
  ordinary buttons.

## 9. Decisions

Recommended option first.

1. **Accounts:** **our own email and password accounts in FastAPI, with server-side
   sessions in an `HttpOnly` cookie** (recommended: no third party, works the same locally
   and in tests, fits the API that owns the data); or **sign in with an OAuth provider**
   (GitHub or Google through Auth.js in Next.js; no passwords to store, but needs provider
   apps per environment and a bridge to FastAPI); or **a hosted auth service** (Clerk or
   Supabase Auth; quickest, but a vendor in every request and in local development).
2. **Leagues:** **private to their owner** (recommended); or **shareable read-only by
   link**, so a friend can follow your league (an easy addition later either way).
3. **Existing saves:** **claimed by the first account created** (recommended); or
   **start fresh**, deleting them in the migration.
4. **Job queue:** **a Postgres table and a worker process** (recommended: no new
   infrastructure, transactional with the data it changes); or **Redis with a queue
   library** (arq or RQ: another service to run and back up); or **in-process background
   tasks** (simplest, but jobs die with a deploy and progress can't be shared between
   API instances).
5. **What becomes a job:** **anything over about a second** (rest of the season,
   playoffs, offseason, finishing free agency and the draft), keeping the week, a
   free-agency day and a draft pick instant (recommended); or **every sim**.
6. **Multi-season sims** ("sim 5 seasons", with progress, using the job queue): **later**
   (recommended: keep M7 on the platform); or **in Milestone 7**.
7. **Hosting:** **one container platform for the web app, API and worker, plus its
   managed Postgres, defined in the repo** (recommended: Render or Fly.io; one vendor, one
   bill, the same containers as CI); or **Vercel for the web app** (first-class for Next.js
   16, with preview deploys per PR) **with the API and worker on a container platform** and
   a managed Postgres (Neon or Supabase); or **one virtual server running Docker Compose**
   behind Caddy (cheapest, but you patch and back it up).
8. **Environments:** **staging deploys from `main`, production after a manual approval**
   (recommended); or **production on every merge to `main`**; or the first, **plus a
   preview environment per PR**.
9. **Monitoring:** **Sentry, structured logs, health checks and an uptime check**
   (recommended); or **OpenTelemetry** traces and metrics into a hosted Grafana (more to
   set up, more to see); or **the host's logs only**.
10. **Quality gates:** **axe on every page and performance budgets in CI, failing the
    build** (recommended); or **reports in CI that don't fail the build**.

## 10. Delivery plan (separate PRs, each with tests)

1. **Background jobs:** the `jobs` table and worker, the long sims as jobs with progress,
   cancel and the league lock, the progress UI, and `make dev-backend` starting a worker.
2. **Accounts:** users and sessions, sign up, sign in and sign out pages, the same-origin
   `/api` proxy, ownership checks on every route (with the every-route test), the
   per-user active franchise, existing saves claimed, and the dev account and e2e sign-in.
   This touches every route, so it may land as two PRs: the backend, then the pages.
3. **Deployment and monitoring:** Dockerfiles, CI image builds, the hosting config,
   staging and production with migrations as a release step, readiness, structured logs,
   Sentry, the uptime check, password reset email, and a deploy runbook in the docs.
4. **Performance and accessibility pass:** the budgets and their CI checks, the slow-read
   fixes, axe on every page, the keyboard and screen-reader fixes, and reduced motion.
