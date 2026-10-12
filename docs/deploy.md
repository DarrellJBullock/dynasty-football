# Deploying and running Dynasty Football

How the game is hosted, how a change reaches production, and what to do when something
goes wrong. Design: [`design/platform.md`](design/platform.md) §5–6.

## What runs where

| Piece | Where | Image / command |
|---|---|---|
| Web app (public) | Render web service `dynasty-web-<env>` | `ghcr.io/darrelljbullock/dynasty-football-web`, `node server.js` |
| API (private network) | Render private service `dynasty-api-<env>` | `ghcr.io/darrelljbullock/dynasty-football-api`; pre-deploy `alembic upgrade head` |
| Job worker | Render background worker `dynasty-worker-<env>` | the API image, `python -m app.worker` |
| Database | Render Postgres `dynasty-db-<env>` (17) | daily backups + point-in-time recovery |

Two environments, `staging` and `production`, are defined in [`render.yaml`](../render.yaml).
The browser only talks to the web app; its `/api/*` goes on to the API privately
(`src/proxy.ts`, `API_HOSTPORT`).

## How a change ships

1. A PR's CI builds both images and smoke-tests them together (`scripts/smoke-test-images.sh`).
2. Merging to `main` runs CI again; when it passes, **Deploy** (`.github/workflows/deploy.yml`):
   1. builds the images once, tagged with the commit, and pushes them to GitHub's registry;
   2. deploys them to **staging**: the API first (Render runs the migrations before
      switching), then the worker, then the web app, and checks `/api/ready`;
   3. waits for a reviewer to approve the **production** environment, then tags the same
      images `production` and deploys them the same way.

Migrations must stay compatible with the previous release for one deploy: the old API
keeps serving while the new one migrates and starts. Add columns as nullable (or with a
default) and remove them a release after the code stops using them.

## Setting it up (once)

You need accounts with **Render**, **Sentry** and an **email service with SMTP** (Postmark,
Resend, Amazon SES, ...). None of this can be done from the repository.

1. **Images.** Merge to `main` once so Deploy pushes the first images (the deploy steps say
   they're skipped). In GitHub, Packages: the images are private by default; keep them
   private and give Render access (next step), or make them public.
2. **Render registry access.** Render → Workspace Settings → Registry Credentials: add one
   named `ghcr` for `ghcr.io` with your GitHub username and a personal access token that
   has `read:packages`.
3. **Blueprint.** Render → Blueprints → New Blueprint Instance → this repository. Render
   creates both environments and asks for every `sync: false` value:
   - `SITE_URL`: the environment's address, e.g. `https://dynasty-web-staging.onrender.com`
     (or your domain);
   - `ALLOWED_ORIGINS`: the same, as a JSON list: `["https://…"]`;
   - `SENTRY_DSN` (API, worker and web): from Sentry, below;
   - `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`: from the email service
     (`EMAIL_FROM` like `Dynasty Football <no-reply@your-domain>`).
   Production is protected (`permissions.protection`): changes there need confirming.
4. **Sentry.** Create two projects, a Python one (API and worker) and a Next.js one (web).
   Put the Python DSN in the API's and worker's `SENTRY_DSN`, the Next.js DSN in the web
   service's `SENTRY_DSN` and in the GitHub repository variable `NEXT_PUBLIC_SENTRY_DSN`
   (it's built into the browser bundle; DSNs aren't secret). Errors are tagged with the
   environment and the commit.
5. **GitHub environments.** Settings → Environments:
   - `staging` and `production`, each with the secret `RENDER_API_KEY` (Render → Account
     Settings → API Keys) and the variables `RENDER_API_SERVICE_ID`,
     `RENDER_WORKER_SERVICE_ID`, `RENDER_WEB_SERVICE_ID` (each service's `srv-…` id) and
     `SITE_URL`;
   - on `production`, **Required reviewers**: that's the approval step.
6. **Uptime.** Repository variables `STAGING_URL` and `PRODUCTION_URL`. The **Uptime**
   workflow checks `/signin` and `/api/ready` every 10 minutes; GitHub emails you when a
   scheduled run fails. (Sentry's uptime monitors can do the same every minute.)
7. Run **Deploy** by hand (Actions → Deploy → Run workflow) to deploy `main`.

## Day to day

- **Logs:** each service's Logs tab in Render. The API and worker write one JSON object a
  line: `request_id`, `route`, `status`, `duration_ms`, `user_id` for requests; `job_id`,
  `kind`, `status`, `duration_ms` for jobs. A job's "queued" line carries the request id
  of whoever started it. Responses carry `X-Request-ID`, so a user's report can be traced.
- **Health:** `/api/health` (the process is up) and `/api/ready` (the database answers and
  its schema is current; 503 otherwise). Render checks the web app at `/signin`.
- **Errors:** Sentry, by environment and release. Cookies, auth headers, passwords and
  reset tokens are scrubbed before they leave.
- **A forgotten password:** users reset it from the sign-in page by email. By hand: Render
  → the API service → Shell: `python -m app.accounts set-password EMAIL`.

## When something goes wrong

- **A deploy failed.** The previous version keeps running. Read the failed deploy's logs in
  Render (a `pre_deploy_failed` is a migration), fix forward, merge again.
- **Roll back.** Render → the service → Deploys → an earlier deploy → Rollback (API first if
  a migration is involved, after checking it's compatible), or run Deploy by hand from an
  earlier commit.
- **Stuck simulations.** A job whose worker died is failed after a minute and its league
  unlocked; the user can run it again. If the worker is down, restart it in Render.
- **Restore the database.** Render → the database → Recovery: restore to a point in time
  (creates a new database), point the services' `DATABASE_URL` at it, redeploy. Practise it
  on staging every few months: restore yesterday's staging into a new database, sign in
  against it, then delete it.
