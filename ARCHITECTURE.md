# Architecture

## Overview

```
┌──────────────────────────── Browser ────────────────────────────┐
│ Next.js 16 client: React 19, Tailwind v4, React Three Fiber     │
│   interactive islands (roster editor, dialogs, 3D field)        │
└──────────────┬───────────────────────────────▲──────────────────┘
               │ fetch /api/* (same origin)    │ streamed HTML/RSC
┌──────────────▼───────────────────────────────┴──────────────────┐
│ Next.js server: proxies /api/* to FastAPI; Server Components    │
│ fetch the API inside <Suspense> with the visitor's cookie;      │
│ static shell is prerendered (Partial Prerendering)              │
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

The browser calls `/api/*` on the web app's own origin, which Next.js rewrites to FastAPI
(`next.config.ts`), so the session cookie is first-party and there's no CORS. Server
Components call FastAPI directly (`API_URL`) for initial page data, forwarding the
visitor's cookie. Every route but `/api/health` and `/api/auth/*` needs a signed-in user
and only reaches the leagues they're a member of (`api/access.py`). In a league,
commissioners run the season and its members, and managers run their own team: every
change route names who may make it (`access.WRITES`), checked before the route runs.
Invite links (`/join?token=…`) let friends join and take an open team; only a hash of
each token is stored (`services/members.py`, docs/design/leagues-with-friends.md). A
commissioner can also share a read-only public link (`/share/{token}`, served by
`/api/public/{token}/…` without a session), and any member can export the league as JSON
(docs/league-export.md).

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
| `users` | email (unique, lower-case), password_hash (Argon2) |
| `sessions` | user_id, token_hash (SHA-256 of the cookie's token; unique), expires_at (30 days, extended as it's used) |
| `password_resets` | user_id, token_hash (SHA-256 of the emailed link's token; unique), expires_at (an hour), used_at |
| `leagues` | user_id (owner; empty only for leagues from before accounts, which the first account takes over), name, abbreviation, salary_cap, players (`men` / `women`: generated players' names and builds, `seed.generator.BODY` / `BODY_WOMEN`) |
| `conferences`, `divisions` | name (+ abbreviation) |
| `teams` | city, nickname, abbreviation (unique per league), primary/secondary colour, stadium |
| `players` | league_id, team_id?, name, position, jersey (0–99), age, height_in, weight_lb, college, years_pro, **overall** (cached), potential, development_trait, injury_status, injury? (description), injury_weeks (games still to miss), injury_count (career injuries from games), retired_year?, is_prospect, scouted, draft_year?, draft_round?, draft_pick? |
| `player_ratings` | player_id PK + 24 attribute columns (0–99) |
| `contracts` | player_id, team_id, start_year, years, salary (yearly cap hit), signing_bonus (30% of total value above the minimum; `Contract.signed`), is_active |
| `dead_money` | team_id, player_id, year (cap year), amount, reason (released / traded / retired) |
| `awards` | season_id, award (mvp / opoy / dpoy / oroy / droy; unique per season), player_id, team_id?, summary |
| `seasons` | league_id, year (unique per league), phase (free_agency → draft → preseason → regular_season → playoffs → offseason), free_agency_day, current_week, champion_team_id?, offseason_log (what the rollover into this season did; JSON) |
| `playoff_seeds` | season_id, conference_id, team_id, seed, division_winner; fixed when the regular season ends |
| `draft_picks` | league_id, year, round, original_team_id, team_id (current owner), season_id? + number? (set when that draft opens, from the original team's finish), player_id? (set once made) |
| `trades` | league_id, season_id, team_id (franchise), partner_id, phase, week, sent / received (JSON: kind, id, label) |
| `free_agent_offers` | season_id, player_id, team_id, salary, years, day, status (pending / accepted / lost / expired) |
| `games` | season_id, week, stage (regular \| playoff), playoff_round?, neutral_site, home/away team, scores (nullable), status, overtime, seed, sim_version, play_log (JSON/JSONB; from SIM_VERSION 1.2 each scrimmage play carries `personnel`, its 22 players and package, and kicks a `returner`); log_compacted (an older season's game trimmed to its scoring plays, injuries and last play) |
| `player_game_stats` | game_id, player_id, team_id + one column per `sim.stats.PlayerLine` field |
| `team_game_stats` | game_id, team_id + one column per `sim.stats.TeamLine` field |
| `franchises` | name, league_id (unique — one career per league), team_id, activated_at (the user's latest = their active franchise) |
| `jobs` | league_id, kind, params (e.g. `{seasons: 5}` for sim ahead), status (queued / running / done / failed / cancelled; one queued or running per league, a partial unique index), progress / total, label, cancel_requested, result (the synchronous endpoint's response, JSON), error, started/finished/heartbeat times |
| `game_plans` | team_id (PK), plan (the plays and calls in it, and its tendencies; JSON). Only the franchise saves one; other teams play to a plan drawn from their roster |
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
| `GET /api/health` | Liveness (no sign-in needed) |
| `GET /api/ready` | Readiness: the database answers and its schema is at this build's newest migration (503 otherwise) |
| `POST /api/auth/signup` `{email, password}` | Create an account and sign in (sets the `df_session` cookie); the first account takes over leagues from before accounts |
| `POST /api/auth/signin` / `POST /api/auth/signout` | Sign in (401 on a wrong email or password, 429 after repeated failures) / out |
| `GET /api/auth/me` | The signed-in account (`has_league` sends a new one to the league builder) |
| `PUT /api/auth/password` `{current_password, new_password}` | Change the password; other sessions are signed out |
| `DELETE /api/auth/account` `{password}` | Delete the account and every league in it |
| `POST /api/auth/forgot` `{email}` | Email a one-time reset link (202; the same answer for any address; 5 an hour per address) |
| `POST /api/auth/reset` `{token, password}` | Set a new password with the link's token; signs the account out everywhere (400 for a used or expired link) |
| `GET /api/franchise` | Active franchise (league, team, season) |
| `GET /api/franchises` | Every franchise, most recently active first |
| `POST /api/franchises/{id}/activate` | Make a franchise active |
| `GET /api/leagues/template?conferences=&divisions=&teams_per_division=` | Editable league spec filled with fictional teams |
| `POST /api/leagues` | Create a league from a spec; creates and activates its franchise |
| `DELETE /api/leagues/{id}` | Delete a league and its contents (not the active one) |
| `PATCH /api/teams/{id}` | Edit team identity (city, nickname, abbreviation, colors, stadium); logged in the League log |
| `POST /api/seasons/{id}/simulate` `{until: next_week \| end_of_regular_season \| end_of_playoffs}` | Play a week (or playoff round) or the rest of a phase; persist scores, stats, play logs; seeds and schedules playoff rounds |
| `POST /api/seasons/{id}/advance` | After the champion: run the offseason (aging, development, retirements, contracts) and create the next season, in free agency |
| `POST /api/leagues/{id}/jobs` `{kind, seasons?}` | Start a background sim (202): `sim_regular_season`, `sim_playoffs`, `advance_offseason`, `finish_free_agency`, `finish_draft`, or `sim_seasons` (sim ahead 1–10 seasons, the franchise on autopilot); 409 if one is already running in the league |
| `GET /api/leagues/{id}/dynasty?from_year=&to_year=` | The Dynasty report for up to 10 seasons: each season's result and awards, and the franchise's offseason after it |
| `GET /api/jobs/{id}` | A job's status, progress (`n of m`, label) and, once done, its result (the matching synchronous endpoint's body) or error |
| `DELETE /api/jobs/{id}` | Stop a job: a queued one at once, a running one after its current week, round or market day |
| `GET /api/leagues/{id}/free-agency` | The market: free agents with asking prices and offer counts, your offers (leading/outbid), this offseason's signings |
| `POST /api/players/{id}/offer` `{salary, years}` / `DELETE` | Make (or replace) / withdraw the franchise's offer to a free agent |
| `POST /api/seasons/{id}/free-agency` `{until: next_day \| end}` | Play market days; after the last, the draft opens |
| `GET /api/leagues/{id}/draft` | The draft: order and picks, the class as scouted (projections until scouted), scouting reports left, your roster count; generates the class the first time |
| `POST /api/players/{id}/scout` | Spend a scouting report on a prospect |
| `POST /api/leagues/{id}/draft/pick` `{player_id}` | The franchise drafts when it's on the clock |
| `POST /api/seasons/{id}/draft` `{until: my_pick \| end}` | AI teams pick until you're up, or finish (auto-picking for you); then undrafted free agents, cut-downs, preseason |
| `POST /api/teams/{id}/cut-down` | Release the lowest-rated players down to 53 |
| `GET /api/leagues/{id}/trades?partner_id=` | Trade center: both sides' players and tradeable picks with values, partners, window, history |
| `POST /api/leagues/{id}/trades/evaluate` | How the other team would react to a proposal (no trade) |
| `POST /api/leagues/{id}/trades` | Propose a trade; it happens if they accept |
| `GET /api/leagues/{id}/history` | Every season (champion, runner-up, awards, the franchise's record and result) and single-season / career records; backfills awards |
| `GET /api/players/{id}/career` | Season-by-season regular-season stats, career totals, awards |
| `GET /api/teams/{id}/contracts` | Payroll now and committed to next season, expiring deals with asking prices (and new deals once re-signed), every contract |
| `POST /api/players/{id}/re-sign` `{salary, years}` | Offseason only: offer an expiring player a new deal; returns accepted, or his price for that length |
| `GET /api/leagues/{id}/playoffs` | Seeds (projected during the season), rounds and games, champion |
| `GET /api/leagues/{id}/schedule?week=` | One week (defaults to the next week to play) |
| `GET /api/games/{id}` | Line score, team & player stats, scoring summary, play-by-play, injuries |
| `GET /api/franchise/next-game` | The franchise's game this week (or playoff round) if it hasn't been played, and whether the user is coaching it |
| `POST /api/games/{id}/coach` | Coach Mode: start coaching the franchise's next game (snapshots both teams) or pick it up again; returns the state |
| `GET /api/games/{id}/coach` | The coached game's state: the next call (situation with the clock before runoff, the AI's suggestion) and every play so far |
| `POST /api/games/{id}/coach/call` | Make the next call `{play, package?, timeout?}`; the snap is played up to the next call. 422 for a call that doesn't fit the situation. With audibles in the game plan, a play call first stops **at the line** (`situation.role: "audible"`, with the look and the audibles); answer `{play: "keep"}` or an audible's key |
| `DELETE /api/games/{id}/coach` | Abandon a game in progress (e.g. one coached on an older engine): it can be coached again or simulated |
| `POST /api/games/{id}/coach/auto` | Let the AI call the next play, the rest of the drive, or the rest of the game (`{scope}`) |
| `GET /api/games/{id}/live` | A live (head-to-head) game as you see it: its status (proposed, declined, in progress, final, settled), your call to make if it's yours (never the other coach's), who the snap waits on, the call clock's deadline, and the plays; 404 if nobody offered. Other members see it without any call |
| `POST /api/games/{id}/live` | Offer to play this week's game between two managers' teams live `{clock_seconds}` (none, 2 min, 10 min, an hour, a day a call); the other manager is notified |
| `POST /api/games/{id}/live/accept` / `decline` | The other manager's answer: a yes freezes both teams and kicks off; a no leaves the game to be simulated from both game plans |
| `POST /api/games/{id}/live/call` / `auto` | Your call for the snap the game waits on (409 when it waits on the other coach; it plays once both have called) / let the AI call the next play, the drive, or the rest of the game for you |
| `GET /api/teams/{id}/game-plan` / `PUT` / `DELETE` | The team's game plan (saved, or suggested by its roster), the choices and what a plan must keep / save the franchise's (422 with the reasons if it can't run; 403 for another team) / back to the suggested plan |
| `GET /api/playbook` | The named offensive plays (category, formation, the engine call, target weights) and defensive calls (shell, man/zone, blitz, forced package) |
| `GET /api/games/{id}/playback` | 3D playback data: typed play records with each scrimmage play's 22 players (rebuilt from today's depth charts, flagged approximate, for games before SIM_VERSION 1.2) and those players' names, numbers, positions, speed |
| `GET /api/leagues/{id}/leaders?category=&limit=` | Season leaders: all categories (top 5) or one (up to 50) |
| `GET /api/leagues/{id}/team-stats` | Every team's season totals, offense and defense (allowed) |
| `GET /api/players/{id}/stats` | A player's season totals and game log |
| `GET /api/franchise/dashboard` | Everything the dashboard needs in one call |
| `GET /api/leagues`, `/api/leagues/{id}` | Leagues |
| `GET /api/leagues/{id}/teams` | All teams with ratings, payroll, cap space |
| `GET /api/leagues/{id}/standings` | Standings by division |
| `GET /api/leagues/{id}/free-agents?position=` | Free agent pool |
| `GET /api/teams/{id}`, `/api/teams/{id}/roster` | Team detail, roster |
| `POST /api/teams/{id}/players` | Create a custom player (409 if full / jersey taken / over cap); commissioners only, logged |
| `POST /api/teams/{id}/signings` | Sign a free agent |
| `GET /api/teams/{id}/depth-chart` | Effective chart: every slot's order, starters fielded, team ratings |
| `PUT /api/teams/{id}/depth-chart/{slot}` | Save a slot's order (may include cross-listed players) |
| `DELETE /api/teams/{id}/depth-chart/{slot}` | Reset one slot to OVR order |
| `DELETE /api/teams/{id}/depth-chart` | Reset every slot |
| `POST /api/teams/{id}/roster-import/preview` | Multipart `file` + `mode` (append/replace); validates without changing anything |
| `POST /api/teams/{id}/roster-import/commit` | Same file again + `skip_invalid`; all-or-nothing by default. Importing (preview and commit) is the commissioner's, and logged |
| `GET /api/roster-import/template.{csv,xlsx,json}` | Downloadable import template |
| `GET /api/teams/{id}/roster-export.{csv,xlsx,json}` | Roster in the import format (`HFD-roster-2026.csv`) |
| `GET /api/players/{id}` | Player with all 24 ratings |
| `PATCH /api/players/{id}` | Partial edit (bio, position, status, ratings); OVR recomputed. The commissioner's (a manager may only change their own player's jersey number: 403 otherwise); what changed goes in the League log |
| `POST /api/players/{id}/move` | The commissioner moves a player `{team_id}` to another team (his contract goes with him, no dead money; renumbered if his number's taken; 409 to a full roster) or, with `null`, to free agency (contract ended, no dead money) |
| `PUT /api/players/{id}/contract` | The commissioner rewrites a contract `{salary, years}` from this season (a new deal's bonus; 409 for a free agent) |
| `POST /api/trades/{id}/reverse` | The commissioner reverses a trade from this season: players and picks go back, the players on the contracts they had, the trade's dead money cleared (409 with why once anyone in it moved, signed again, or a pick was used; or if a roster would go over 53). The trade center lists the season's trades for commissioners (`season_trades`, each with why it can't be reversed) |
| `GET /api/teams/{id}/owner` | The team's owner (name, priority, patience, confidence, hot seat) and fans (market, mood with this season so far and what moved it), this season's goals (met, missed, on track, behind) and the last review (each goal, what moved confidence and the fans, before and after). A league from before owners gets them on first read |
| `GET /api/leagues/{id}/rules` / `PATCH` | The league's rules (roster size, salary cap, cap growth a season, playoff seeds per conference or automatic, regular-season weeks), what they come to (seeds, byes), and why they can't change now / change them (commissioners; only between seasons: after the champion and before week 1, 409 otherwise). A lower roster limit in the preseason cuts AI rosters now; a new length before week 1 draws the coming schedule again (in the offseason, the next one's); cap growth applies each offseason. Logged and told to members |
| `GET /api/leagues/{id}/rollback` / `POST` | The week (or playoff round) that can be rolled back / roll it back (commissioners): its games are unplayed, box scores, injuries (to the snapshot taken before it), the playoff seeds and later rounds, the champion and awards, and the week's notifications go; rosters stay. Only the latest, once; refused while a game is coached or offered live |
| `GET /api/leagues/{id}/log?before=&action=` | The League log, newest first, 50 at a time (`more`): who, what, when, and each change's before and after. Every member sees it |
| `POST /api/players/{id}/release` | Release to free agency |

Interactive docs: `http://localhost:8000/docs`.

## Frontend

- **Routing:** App Router, in two route groups with their own root layouts: `(auth)` has
  `/signin` and `/signup` (no sidebar); `(app)` has the game, with the sidebar and its
  account menu (the email, Account, Sign out). `src/proxy.ts` sends visitors without a
  session cookie to `/signin?next=…`. `/account` changes the password or deletes the
  account. `/` dashboard, `/roster`, `/depth-chart`, `/league`,
  `/leagues` (saved franchises), `/leagues/new` (league builder), `/schedule?week=`,
  `/games/[id]`, `/playoffs`, `/contracts`, `/free-agency`, `/draft`, `/trades`, `/history`, `/stats?view=teams&category=`, `/players/[id]`. Every page reads the
  active franchise, so switching franchises re-points the whole app.
- **Data loading:** each page renders a static shell + `<Suspense>` skeleton; an async
  Server Component fetches from the API (`src/lib/api.ts`) and streams in. Errors are
  captured with `attempt()` and rendered by `ServerError` (offline / no league yet, with
  a link to build one); a 401 there redirects to `/signin`.
- **Interactivity:** the roster screen is a client component (`RosterManager`) seeded
  with server data, then mutating through the API and updating local state; the team
  header is re-fetched after each mutation.
- **Freshness:** mutations go straight to the API, so Next.js can't see them. Creating or
  switching the active franchise does a full page load (`lib/navigation.hardNavigate`),
  because the client router cache can otherwise reuse pages rendered for the previous
  franchise. Covered by `e2e/freshness.spec.ts`.
- **Read performance:** `Game.play_log` and `Season.offseason_log` (tens of KB each) are
  deferred columns, so lists of games and seasons stay small; `python -m app.perf`
  (`make perf`) times every read on a league with seasons played, and CI holds each to
  600 ms and 80 queries.
- **Accessibility:** WCAG 2.2 AA, checked by axe on every page in e2e. A "Skip to
  content" link, one `h1` per page, dialogs that trap and return focus, labelled 3D views
  (decorative; the play-by-play and score bug carry the same information as text), and
  `prefers-reduced-motion` honoured (`lib/motion.ts`: no camera easing or orbit, replays
  off by default, CSS animations finish at once).
- **Season stats** are aggregated on read from `player_game_stats` / `team_game_stats`
  (`services/league_stats.py`) — no denormalized season tables to keep in sync. Box-score
  column groups are shared between the game and player pages (`lib/stats.ts`).
- **Season simulation:** a week ≈ 0.5 s, a season ≈ 8 s including writes.
  `services/season.py` snapshots every roster + depth chart once per run, seeds each game
  from (league, year, week, game id), and stores the box score rows and play log. A week,
  a market day and a draft pick are plain requests; the rest of the season, the playoffs,
  the offseason and finishing free agency or the draft are **background jobs**
  (`services/jobs.py`, run by `app/worker.py`): the controls start one, poll its progress
  (`useJob`, a progress bar with Stop), and every season carries its league's
  `active_job`, so any page's controls pick a running job up again. While a job runs, the
  league's changes are refused (`api/locks.py`). Sim controls call `router.refresh()`
  afterwards so the current page re-renders.
- **Dialogs** render through a portal to `<body>`: a `.panel`'s `backdrop-filter` traps
  `position: fixed` descendants, which hid dialogs opened from inside panels.
- **Pure logic** (`lib/format.ts`, `lib/roster.ts`) is framework-free and unit-tested.
- **Design system:** tokens in `src/app/globals.css` (`@theme`): ink surface scale,
  chalk/mist text, gold accent, Barlow Condensed display font, `.panel`/`.btn`
  component classes. Team colours are injected as `--team-primary/secondary`.
- **Depth chart editor:** dnd-kit sortable lists (pointer, touch, keyboard) with arrow
  buttons as a fallback. Edits save immediately and optimistically; a failed save reverts
  and shows the error, and only the newest response is applied.
- **3D:** `components/field/` (R3F, client-only via `next/dynamic({ ssr: false })`):
  `layout.ts` holds the field geometry (yards; field x 0–120 along, y 0–53⅓ across; the
  scene is centered on midfield) and camera presets — pure and unit-tested; `fieldTexture.ts`
  paints every marking onto one canvas texture (one draw call); `Stadium.tsx` adds goal
  posts, stands with an instanced crowd in team colors, light towers, lighting, and the
  line-of-scrimmage / first-down overlays; `CameraRig.tsx` eases between presets
  (overview orbit, sideline, end zone, all-22). The dashboard shows it with camera buttons.
  `components/field/players/` holds the players: `poses.ts` (joint angles for each pose,
  blending, a distance-driven run cycle, builds from height and weight), `formations.ts`
  (alignments in the play log's personnel order), `kit.ts` (home/away uniforms with
  readable numbers), `PlayerFigure.tsx` (the jointed low-poly figure and the football, each
  posed every frame by a *driver* function, so 22 players animate without React
  re-renders), and `Lineup.tsx` (both teams in stance, used on the dashboard).
  `components/field/playback/` plays a game back: `choreograph.ts` turns each play record
  into a **timeline** (`timeline.ts`: every player's path and pose keys, the ball held / in
  flight / at rest, the play's moments, any flag) with a script per play type, so the
  recorded carrier reaches the recorded spot where the recorded tacklers meet him; it's
  pure, seeded by game and play number, and chains each snap to where the last play ended.
  Kick units and conversions, which the play log doesn't list, are filled from the team's
  players in the game. `assignments.ts` holds what every player does on each named play
  (formation, routes, run scheme, play action, screens) and defensive call (zones, man
  matchups, blitzers), keyed by the backend playbook's keys; plays from before named
  calls fall back to generic motions. `PlayScene.tsx` renders a timeline, sampling it every frame from a
  shared `PlayClock` (`clock.ts`) that the scene advances and the controls seek, so playing
  re-renders nothing. `components/watch/WatchView.tsx` is the Watch page: one request loads
  the game (`/api/games/{id}/playback`) and every play is choreographed in the browser
  (~20 ms a game), so stepping and scrubbing are instant.
  `components/coach/CoachView.tsx` is Coach Mode's call screen (`/games/[id]/coach`;
  `/coach` renders the franchise's next game the same way, or `LiveView` when it's against
  another manager): each call posts to the coach API (a live game's `/games/[id]/live` passes
  its own calls and polls while it waits on the other coach),
  then reloads the game's playback (which, for a game in progress, is the replay so far)
  and `PlayReel` plays the new plays in 3D. `components/broadcast/BroadcastOverlay.tsx`
  draws the broadcast graphics over both views (HTML over the canvas): the score bug and
  banners, worked out by `lib/broadcast.ts` from the play record and its timeline.
  `playback/director.ts` is the broadcast director: a shot list per play (cues of
  `(time, shot)` from its moments and type); `CameraRig` cuts on a new shot and eases
  while following the ball within one. `playback/replay.ts` picks which plays get an
  instant replay (the highlight rule) and its angle; `useInstantReplay` runs it on the
  shared `PlayClock` (back to the snap at half speed, then on to the play's end).
  `lib/gameStats.ts` folds running player and team stats from the play events (the same
  rules as the backend's `stats.py`) for the stat lower thirds, drive summaries and the
  halftime and final cards.

## Testing

| Suite | Tooling | What |
|---|---|---|
| Backend domain | pytest | OVR math, salary curve, jersey allocation, roster template |
| Backend generator | pytest | determinism, structure, roster composition, unique jerseys, cap compliance, schedule validity |
| Backend API | pytest + TestClient | every endpoint incl. 404/409/422 paths |
| Backend roster import | pytest | readers per format and bad files, header/position aliases, heights, rating fill/caps, errors vs warnings, preview/commit modes, skip-invalid, templates round-trip; export → re-import is lossless in every format |
| Backend leagues | pytest | spec validation, templates, creation (generated/empty rosters, custom identities, schedules for small leagues, determinism), franchise switching, team edits, protected delete |
| Special teams | pytest + Vitest | onside recovery rate (about one in eight), hands make the difference, recovery spots; squib spots; the AI's kickoff and conversion rules; onside kicks changing possession in a game; the play-by-play text; the coach's kickoff and conversion decisions (and choosing two), validation; a coached game from an older engine refused and abandoned; playback knows the recoverer's team; 3D squibs and onside recoveries (recorded spot, recoverer on the ball); the call screen's kicking decisions |
| Coach Mode UI | Vitest + Testing Library + Playwright | start, the playbook opening on the AI's pick, calling a play from another tab, Call it with a timeout (disabled while the clock is stopped), defensive personnel, the AI taking a play / drive / the rest of the game (with a confirm), the final screen, errors, hiding 3D, a game already played; the Dashboard's Coach this game link; Playwright coaches the franchise's game from Play Game to the box score |
| Coach Mode | pytest | a coached game stops at the first call, plays to the end on the AI's suggestions and replays exactly, partial replays are prefixes of the full game, the user's offensive and defensive calls (and package) are the calls made, a timeout saves the runoff, autopilot finishes the game, team snapshots play identically; call validation; the API: next game, start (and resume), wrong-side and unknown calls refused, AI play/drive/game, the week blocked while in progress, the finished game stored like a simulated one and left alone when the week is simmed (its injuries settled), only the franchise's next game coachable, roster moves don't change a game in progress |
| Playbooks | pytest | plays are complete engine calls, concept tables name real plays and shells, AI choices match the coarse call, concepts break even against the AI's mix, every snap is a named call, concepts change outcomes (Smash vs Cover 2 / Cover 4, runs vs two-high / single-high), plays steer the QB's target, the playbook API, play names on game detail and playback |
| Simulation | pytest | determinism, score/clock/down invariants, box-score consistency, overtime rules, Coach seam, AI 4th-down/kneel calls, depth-chart lineups, calibration targets, rating sensitivity |
| Season | pytest | week/season simulation, persisted stats match scores, standings and dashboard follow results, reproducible seeds, injured QB benched, schedule/game endpoints, deleting played leagues |
| Season stats | pytest | leaders equal summed box scores (and "long" columns are maxima), released players keep their last team, player totals equal the game log, team totals reconcile with standings and league-wide (yards gained = allowed, turnovers = takeaways) |
| Playoffs | pytest | seed counts, pairing and reseeding, round names, each tiebreaker, division winners seeded first; full bracket to a neutral-site champion, offseason 409s, playoff games excluded from standings and stats, projected bracket, small one-conference leagues |
| Offseason | pytest | growth/decline/retirement curves, contract lengths; rollover creates the next season and schedule, ages players, retires and refills (full rosters, under the cap, one active contract each), determinism, retired players leave free agency, dashboard recap, a full season → next season through the API, multi-year stability |
| Spoken commentary | Vitest + Playwright | voice choice (English, local first, stable, shared when there's one, none), the two deliveries, speaking time, first clauses, the pacing plan (fits, cut short, left to captions; most of a real call is spoken), the speaker (one line at a time in its voice, rate, pitch and volume; the crowd lowered while talking), the hook (lines on their moments at the sound's volume, stopped on a seek, quiet in replays and with Commentary off); Playwright hears lines spoken in Chromium |
| Commentary | Vitest + Testing Library + Playwright | every kind of play called within its timeline and in order, players by last name (tacklers, receivers, defenders, returners), kicks, scores and fouls; the analyst after the whistle (a wiped-out foul, an injury, the final score); the same play phrased the same way; no gendered words in any phrasing; captions show the current line for a few seconds and label the analyst; the Watch page's Captions switch shows the call in time with the play and is remembered; Playwright sees captions during a play |
| Sound | Vitest + Testing Library + Playwright | a play's cues (the snap count before the snap, hits and whistles in order, big hits on sacks, kicks, flags without a reaction), the home crowd cheering and groaning (half at a neutral site), its level by quarter, score and playoffs, cues played once as the playhead passes and not on a scrub; the hook (off until turned on and remembered, the engine started by the click, the mix and the crowd level, replays quieter without reactions, quiet when the viewer goes away); the controls; Playwright turns sound on in Chromium (the audio context runs and the snap count, snap and whistle play) and it's remembered after a reload |
| Unity viewer | Unity Test Framework + Vitest + Testing Library + Playwright | athletes posed where and how the timeline says, numbers in the kit's color that read left to right from the front under the mirrored root, boxes wound to face outward, the stadium (two goalposts, four light towers, ~4,900 fans recolored about half in the home colors), skin tones and proportions matching the browser's; Unity's sampler (positions, facing, all 13 joint angles, hip height, ball) against the browser's own samples of a run, a pass and a punt (shared fixtures, rewritten by a Vitest test that fails when they're stale); the page's messages and the coordinate mapping; the bridge (finding the build, starting, loading plays, frames, errors before ready); the camera's motion (cuts, easing, following, less motion); the Renderer switch on the Watch page and in Coach Mode (only with a build, remembered and shared, falling back to Classic on an error and remembering that); one Unity per page (started once, the canvas moved to whichever viewer is shown and parked between, never taken back from a newer viewer, each game's field sent once, a failed start retried); Playwright loads Unity in Chromium, plays, steps to the next play, reloads into Unity and switches back, coaches two calls with the same Unity canvas, and runs axe with Unity drawing (skipped without a build) |
| Fatigue | pytest + Vitest + Testing Library | energy cost by position, play length and stamina; recovery on the sideline and at breaks (fresh players kept out of the table); tired players' physical ratings (cached copies) and injury odds; subs out below the line and back only above the sub-in line, in depth order, never QBs or linemen, thin depth playing on, stand-ins last; the Rotation tendency and generated plans leaning on depth; in games: starters most, backups rotating in, determinism, low-stamina lines wearing down, snap counts equal to the recorded personnel (not pre-snap fouls); Coach Mode's tired players; the game page's snap counts and shares, and the call screen's energy meters |
| Penalties | pytest + Vitest | every foul named and rated; awareness scaling (bounded) and sloppier players drawing more flags; which plays allow which fouls (offensive fouls only on gains, defensive holding only short of its yards, no personal foul on a score, grounding only on throwaways, nothing on turnovers); enforcement: false start and holding back the offense (half the distance at most), offside forward (a first down only past the line to gain), defensive holding an automatic first down, a personal foul added to a play that stands, grounding costs the down; the box score charges the team that fouled; calibration (5–7 flags, 40–60 yards a team a game); the FLAG banner and 3D replay name the foul |
| Injuries | pytest | earlier injuries raising the odds (capped), questionable players playing hurt (and snapshots keeping it), the career count, contact and toughness odds, injury table ranges, injured players sit for the rest of the game, play outcomes unchanged before the first injury, determinism, status mapping, weekly countdown (hand-set statuses untouched), lineups skip the injured, dashboard report, game-page list, manual healing, offseason healing |
| Contracts | pytest | preferred lengths, length premiums, overview and payrolls, window timing, counter-offers and deals, already-signed / not-expiring / over-the-cap / free-agent rejections, rollover keeps re-signed players and lets the rest go (AI still re-signs), offseason signings start next season, dashboard reminder |
| Free agency | pytest | daily demand curve, offer ranking (money, then contenders, then earliest), market opening (AI bids only for lost positions, never for the franchise), view, a premium offer wins on day 1, a lowball waits for the last day, offer rules (free agents only, cap, replace, withdraw), closed outside the market, closing fills rosters and starts the preseason, AI never re-signs its own departures, determinism, dashboard alert |
| Draft | pytest | class quality by rank, rookie scale, potential grades, draft order (worst first, champion last, deterministic ties), stable scouting error; class generated once and hidden from free agency and signings; scouting budget and reveals; draft opens after free agency with a 7-round order; franchise picks only on the clock with slotted rookie deals; finishing (AI rosters at 53 and under the cap, undrafted become free agents, early picks better than late, franchise must cut to 53 before week 1, the finished draft stays visible); determinism; prospects skip aging; dashboard alert; recap rookies |
| Trades | pytest | value curves (stars, age, upside, position, contracts), pick decay, AI margin and need bonus; trade center (partners, assets by value, next year's picks); lopsided offers refused; accepted trades move players, contracts, depth charts, jerseys, and log history; traded picks follow their original team into the draft order ("via"); proposal validation; roster and cap limits for both sides; window (deadline, playoffs, draft) |
| Dead money | pytest | bonus share and remaining proration; generated deals carry bonuses; releases charge the right cap year (next season's in the offseason) and show in payroll, cap space, and the Contracts page; minimum deals cost nothing; dead money blocks signings over the cap; new deals include bonuses; traded players leave their bonus behind and move on a bonus-free deal; mid-deal retirements; roster import replacement creates none |
| History | pytest | award scoring and winners (MVP win bonus, rookies, minimum games), summaries; awards decided with the champion, once, and backfilled; season archive (champion and runner-up from the final, franchise record and result); records match the season leaders; career totals match season stats; careers and rookies across seasons |
| Playback | pytest | every scrimmage play records 11 + 11 players from the right rosters (and everyone its events name), kicks name a returner, stand-in ids map to positions; the playback API types every event, resolves every player to the right team, rebuilds approximate lineups for old logs, handles unplayed and missing games |
| 3D field | Vitest | field geometry (lines, numbers, pro hashes, direction), camera presets (framing, both directions, clamping, orbit), the field painter against a recording canvas, camera buttons; Playwright switches cameras on the dashboard |
| Stat overlays | Vitest + Testing Library + Playwright | running player and team stats from events (penalty-wiped plays don't count, stand-ins never credited), matching the box score; whose stat line a play puts up and its wording; drive summaries (still going, touchdown, interception, end of half; kicks aren't drives); halftime and final; the overlay shows the lower third and final card after the whistle, not before and not during a replay, and drive summaries; Playwright sees the score bug on the Watch page |
| Instant replay | Vitest + Testing Library | which plays get a replay (big runs from the reverse angle, passes from the skycam, ordinary plays none, kicks from the kick) and its stretch; on the Watch page the replay rolls after the play (angle, half speed, badge, the result held), straight-through play waits for it, then carries on; Skip replay and the setting; Coach Mode's reel replays in multi-play reels only |
| Broadcast director | Vitest + Testing Library | shot lists for runs, short and deep passes, touchdowns, field goals and kicks; every shot held long enough (touchdowns cut at once); the shot at any moment; the new shots' framing (tight low and on the ball, wide high, reverse on the far side, skycam behind the offense either way); the Watch page defaults to Broadcast with the play's cues |
| Broadcast graphics | pytest + Vitest + Testing Library | play logs record timeouts at the snap and each play's seconds; the running game clock (snap to whistle, old logs, never below zero), the pre-snap play clock, the score going up at the touchdown, down text, banners for every kind of moment and one at a time; the score bug's contents and timeouts, the clock running and the banner and points at the touchdown; the Watch page and Coach Mode reel carry it |
| Audibles | pytest + Vitest + Testing Library + Playwright | disguise rates by awareness (bounded), honest vs disguised looks (personnel never hidden, faked blitzes), the formation the defense sees; no audibles, no stop; stopping at the line on offense and defense with the call, look and audibles; keeping every call plays the game unchanged (the look's own stream); an audible switches the call (`audible_from`) and replays exactly; what can be said at the line; audibles in a plan (up to three, no repeats, from the plan); the API flow; the At the line view (look in words, keep or audible, no playbook or timeout) and the editor's audible picks; Playwright saves audibles and switches at the line |
| Game plans | pytest + Vitest + Testing Library + Playwright | a whole-book, all-zero plan plays a game exactly as before plans (pinned play log), the AI calling only the plan's plays and calls, each tendency moving its rate (pass, deep, play action, blitz, man), fourth downs and two-point tries, what a plan must keep, roster-based plans, snapshots keeping the plan (and older ones neutral), the API (view, save, reset, only your team, the engine using it), Coach Mode's AI following it; the editor (groups, suggestions, what's missing, save and reset, server errors); Playwright edits and saves a plan |
| Sim ahead | pytest + Vitest + Testing Library + Playwright | several seasons as a job (labels, exact progress, the next preseason, three champions), the franchise on autopilot (re-signs, drafts, cut to 53, under the cap), stopping between weeks and carrying on, 1–10 seasons, params only for sim ahead, the league lock; the Dynasty report (oldest first, the offseason after each season, up to 10 seasons); compaction (which games, the box score page unchanged, nothing to watch, the last two seasons untouched, what a compacted log keeps); the controls (choose seasons, the report link, from free agency, stopped, failed), the report page, History's link, compacted notes; Playwright sims a season ahead and reads the report |
| Performance and accessibility | perf tool + Playwright + Vitest | `app.perf` builds seasons and times every API read (CI: 600 ms and 80 queries per read); LCP under 2.5 s and layout shift under 0.1 on the dashboard, roster, schedule, game and Watch pages; three.js only on pages with a 3D view; axe (WCAG 2.2 AA) on every page, fresh and with a week played, signed in and out, and one `h1` each; a keyboard-only sign-in, skip link and sim; reduced motion (replays start off, the hook follows the system setting) |
| Deployment and monitoring | pytest + Vitest + Playwright + CI | readiness (unmigrated vs current schema), request ids (given or made), each request logged with its route template and user, JSON log lines, Sentry off without a DSN and its scrubbing, email to an outbox or the log, password reset (the emailed link works once, signs out everywhere, expires, the same answer for unknown addresses, a few an hour, removed with the account); the proxy (`/api` to `API_URL` or `API_HOSTPORT` with a request id, sign-in redirects, public pages); the forgot and reset forms; Playwright resets a password from the emailed link; CI builds both images and smoke-tests them together (migrate, API ready, web app up, sign up through the proxy, worker running) |
| Accounts | pytest + Vitest + Testing Library + Playwright | sign up (normalized email, the cookie's flags, rules), sign in and out (the same answer for an unknown account), rate limiting and its window, the first account taking over leagues from before accounts, expired and extended sessions, only token hashes stored, changing the password signing out other browsers, deleting the account and its leagues, the admin reset, the seeded dev account; each account's own leagues and active franchise; **every route with an id answers 404 to another account** (walked from the OpenAPI schema), and the routes without ids are a known list; signed-out visitors get 401; the league limit; changes from other sites refused; the forms (sign in back to `?next=`, errors, sign up to the league builder, safe `next`), the account page and the sidebar menu; Playwright signs out, is sent to sign in, signs up a second account that can't open the first one's games, and signs back in to where it was headed |
| Members | pytest + Vitest + Testing Library + Playwright | the creator is commissioner and runs their franchise; invite links (only a hash stored; preview; join with an open team, becoming active; a taken team or a second team refused; expired, revoked and wrong links 404; only commissioners make and see them; joins wait for a running sim); managers run only their team and see the whole league; commissioners run the season and stand in for a member's team; coaching only your own games; a member without a team can't trade or draft; **every change route has a rule** (walked from the OpenAPI schema); leaving, removal back to the AI, the last commissioner handing over, deleting an account leaving shared leagues to the others; display names (trimmed, never the email); members rows deleted with the league; the members page, join page and display-name form; Playwright: a commissioner invites, a friend signs up from the link, joins, sets a name, and is refused the commissioner's team |
| The season together | pytest + Vitest + Testing Library + Playwright | ready check-ins (only managers with a team; reset by advancing); the commissioner advancing one step through every phase, refused to managers and while a sim runs; the daily advance (once a day at its time, never on being set, off again) and settings' validation; the draft clock (AI teams pick up to a manager, whose clock starts; a manager's pick lets the AI pick on; a clock that runs out picks by need; the worker's tick; no clock in a league played alone); games between two managers aren't coached; sim ahead refused with several managers; the turn panel, the commissioner's league settings (time zones both ways), managers' sim controls; Playwright: two managers check in, the commissioner advances, both dashboards move on |
| Trades between managers | pytest + Vitest + Testing Library + Playwright | an offer (with a note) waits for the other manager, who sees it and accepts, and both see the trade from their own side; rejecting, withdrawing, and who may do which; a counter-offer goes back and replaces the first; AI teams answer at once and members' teams only by offer; an offer the window, a roster or a payroll won't allow isn't sent; expiry; an offer whose player moved, or whose manager left, isn't valid; a completed trade voids other offers with its players; the veto window (the commissioner vetoes or approves; the trade goes through when it ends; settings of none, 24 or 48 hours); offers deleted with the league; the trade desk's offers, counter-offers (sides swapped) and the commissioner's veto; Playwright: an offer with a note, a counter-offer from the other browser, and a yes that moves the players |
| Notifications | pytest + Vitest + Testing Library + Playwright | the inbox (lists, counts, marks read; each person's own); a key notifies once; what notifies (a friend joining, ready check-ins nudging the last manager and the commissioner, advancing with each manager's result, trade offers from the receiver's side and their answers, the veto window, the draft clock); email off by default, chosen by kind, sent by the worker's tick; notifications deleted with their league and account; the inbox page, email settings, the sidebar's badge (polled, told by the inbox) and refreshing on return; Playwright: a friend joins and offers a trade, the badge counts two, opening one goes to the trade desk, and reading the rest clears it |
| Sharing and export | pytest + Vitest + Testing Library + Playwright | the public link (anyone with it sees every public read without an account, never contracts; only its own league's games; a new link replaces the old, revoking stops it, a made-up one is not found; only a commissioner shares; its token never in request logs or Sentry); the export (a member downloads it as a file; every team, player, rating, contract and game; nothing private: no emails, accounts, tokens or big logs; strangers can't); the Members page's sharing panel; shared views link within the link with nothing to sim or coach and no player pages; Playwright: a commissioner shares, a visitor without an account goes from the standings to a box score, the league downloads as JSON, and the link stops working; axe on every public page signed out |
| Legacy | pytest + Vitest + Testing Library + Playwright | the legacy score (production ranked within each position, so a lineman's snaps count like a passer's yards; awards, titles, seasons), the ballot (the bar, a few a year, ties), a case in a line; the vote (after the wait, once a year, near misses kept, never twice); an AI team retires its inductee's number and never reissues it; a member's team is asked and decides (only a retired player who played there; never twice); the offseason holds the vote; team record books (single game, season, career; its own games); the export and league deletion; the Hall of Fame and Records pages and the player page's badges; Playwright: an inductee on the Hall of Fame page, his number retired from the record book, and his page's badges |
| Staff | pytest + Vitest + Testing Library + Playwright | staff made within each role's bounds; salaries by role and rating; Coach of the Year (the biggest turnaround; a first season counts as none); every team's five, once, the same way from the league's own seed (the default league's players unchanged); a new league's staff from the start (a women's league's names); the staff page and the league's coaches; a season on every staff member's record with the champion, and one Coach of the Year; the offseason ages them; the export and league deletion; the Staff page (cards, contracts, careers, the head coaches, Coach of the Year); Playwright: our staff, another team's, and the league's head coaches |
| What staff do | pytest + Vitest + Testing Library + Playwright | an average staff changes nothing; better coordinators grow young players faster (more at their specialty; the head coach a share) and slow veterans' decline, poor ones the reverse, within bounds; who coaches whom; development scaled without new draws; scouts (projection error, reports a class) and trainers (layoffs; a week and season-ending injuries unchanged); each role's effect in a line; the offseason, the draft board and injuries use each team's staff; the player page's coaching; Playwright: the staff cards' effects and a quarterback's coaching |
| The coaching carousel | pytest + Vitest + Testing Library + Playwright | retirement by age; AI teams keep good, younger staff; the best hire the budget allows (else the cheapest); payroll as salaries and dead money; letting staff go (dead money for every season left), hiring into an open job within the budget, extending in the final season; only the team's manager or a commissioner; the offseason (retirements, an AI head coach fired after losing, contracts ending, newcomers on the market, AI teams filling every job while a member's stays open, the member told); autopilot runs a member's team like an AI's; the preseason's interim hires; the staff budget setting; the Staff page's budget, open jobs, market and moves; Playwright: letting the scout go and hiring another off the market |
| Facilities | pytest + Vitest + Testing Library + Playwright | level 1 adds nothing and each level adds more (development, layoffs, projections, reports; within the bounds); upkeep and each level's effect in a line; an AI team builds its weakest it can afford; an upgrade is paid now (in the payroll) and arrives at the next offseason, once at a time, within the budget; a budget that can't keep up loses levels and tells a member; AI teams build in the offseason (members' don't); facilities add to the staff's effects (and the player page says so); the export and league deletion; the Staff page's facilities; Playwright: building the training facility's next level |
| Owners and fans | pytest + Vitest + Testing Library + Playwright | markets a quarter small, half medium, a quarter large; where a roster stands (even thirds); goals from the owner and the roster (targets from the season's length); fans following the season (record scaled by games played, playoffs, title, stars) and drifting back between seasons; goals met, missed or open, and on track; a patient owner forgiving more; the owner's word; owners made once and the same for the same league; goals for every team by the preseason; a new league has owners at once; the card through a season; every owner's review at the champion (confidence and fans as the parts add up), a rolled-back final taking it back and the same final giving the same review; next season's goals; owners in the export and gone with the league; the card (goals, meters, what moved them, the review, hot seat, no goals yet); Playwright: goals in a fresh league, a season simulated, the review on the Dashboard |
| League rules | pytest + Vitest + Testing Library + Playwright | the rules as they are (53, no growth, seeds by conference size, 17 weeks), only between seasons, the commissioner's and logged and told to everyone, out-of-range values refused; a smaller roster cuts AI teams now and members before week 1 (and the dashboard says so), a bigger one has room; the cap grows by its rate each offseason (none by default); fewer seeds and rounds, back to automatic; a new length draws this season's schedule again before week 1, or the next season's in the offseason; the panel (everyone sees it, the commissioner changes only what changed, back to automatic, locked mid-season, errors); Playwright: a commissioner changes every rule, the schedule and AI rosters follow, and the rules lock once a week is played |
| Reversing trades and rolling back a week | pytest + Vitest + Testing Library + Playwright | a reversed trade puts players (on their old contracts), picks and dead money back as they were, is marked and logged and told, and can't be reversed twice; refused once a player moved on or signed a new contract, for last season's trade, and to a manager (who doesn't see the season's trades); a rolled-back week has no results, box scores or week notifications, its injuries, phase and week as before, is logged, can't be rolled back twice, and plays the same again; the last regular week takes the seeds and first round with it, the final the champion and awards, each coming back the same; refused while a game is coached and to a manager; the season's trades list (reverse with a confirm, why not, reversed), the rollback panel; Playwright: a commissioner reverses an AI trade on the Trades page and rolls back week 1 from the League log |
| Commissioner edits and the League log | pytest + Vitest + Testing Library + Playwright | the commissioner edits any player and every member sees exactly what changed; a manager only changes a jersey number, and neither adds nor imports players; an edit that changes nothing isn't logged; moving a player to another team (contract kept, no dead money, off the depth chart, numbers unique), to free agency and back, refused to a full roster or by a manager; rewriting a contract (one active, the log's before and after), refused for a free agent, a manager or out of range; team edits, settings, role changes and removals, vetoes logged; the log's pages and filter, strangers refused, deleted with the league; the commissioner panel (move, free agency, contract, errors, the edit dialog), the log page (changes, filter, older entries, empty), the roster without commissioner controls; Playwright: a commissioner edits a contract and frees a player, then a manager reads it in the League log and can't create players |
| Playing head-to-head | pytest + Vitest + Testing Library + Playwright | an offer and a yes (notifications both ways, managers' names), a no simulated as ever, only this week's game between two members (and only listed clocks); each snap waits on both calls made blind (nothing plays, a second call refused), "Your call" told; both handing the game to the AI finishes it; a call clock has the AI call for whoever ran out; the 3D playback follows the game; the week finishes an unfinished game (its calls stand); watchers never see a call; live games deleted with the league; the screen: offering with a clock, yes and no, waiting blind then polling to the snap, the deadline, watching; Playwright: two browsers agree, call a snap blind, and hand the rest to the AI |
| Head-to-head (engine) | pytest | the kickoff is one call and each snap both; a snap waits, blind, for both calls; a whole game replays the same from the same calls (and part way, to the same point); both on autopilot is the AI's game; one side on autopilot is Coach Mode; both sides may audible at the line, the offense first |
| Background jobs | pytest + Vitest + Testing Library + Playwright | every kind as a job (progress, labels, the same result as the synchronous endpoint), the season through the draft as jobs, a job that can't run fails with the reason, one job per league and the league lock (changes 409, reads fine, other leagues free), stopping between weeks and carrying on, one-step jobs finish once started, the worker's claim-and-run loop, dead workers' jobs failed, league deletion; the controls start jobs, show progress and Stop, report results and failures, and pick up a running job; Playwright sims the season in the background, leaves for the Dashboard and finds it running there |
| Watch Mode | Vitest + Testing Library + Playwright | the highlight rule (scores, turnovers, 20-yard plays, missed kicks; not plays called back), stepping through just the highlights with the URL in step, opening straight into highlights playing through; Schedule cards with Watch (played) and Coach (the franchise's game this week) links; the box score's Highlights link; Playwright watches a game from the Schedule and steps through its highlights |
| 3D playback | Vitest + Testing Library + Playwright | choreographer invariants for every play type (22 players on the field and in bounds, ordered paths and moments, the ball accounted for throughout, the recorded spot reached, tacklers meeting the carrier, touchdowns crossing the goal line, kicks returned to the recorded spot, field goals through or wide of the uprights, stand-ins filling kick units, determinism, hash spotting, ends switching by quarter); timeline sampling and the play clock; the Watch view's controls (play/pause, scrubbing, replay, speed, cameras, auto-advance, keyboard) with the scene mocked; Playwright watches a play from the play-by-play, scrubs, and steps through the game |
| 3D assignments | Vitest | every named play and call has a plan with known routes; every pass play completes soundly against every call and every run gains the recorded yards against every call; formations and shotgun snaps; the target's route stretched to the air yards; Smash's corner and hitches; blockers stay in; Power and Counter pullers; Toss pitches; outside runs bounce wide; play-action fakes and the boot; screens; Cover 3 / Cover 2 landmarks; man trails; blitzers and Fire Zone's dropping end; prevent; old logs |
| 3D players | Vitest | every pose valid, the run cycle (period, opposed legs and arms), carry and throw, leaning arms reach forward, blending, builds and hip heights, formations (order, packages, sides, both directions), uniforms (home/away, readable numbers), skin tones |
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
servers or dev data. CI runs them in their own job and uploads traces on failure.

## Future architecture (planned)

### Simulation engine (`backend/app/sim/`)

Design and calibration targets: [`docs/design/simulation-engine.md`](docs/design/simulation-engine.md).

- **Pure and deterministic:** `simulate_game(home, away, seed)` takes two `SimTeam`
  snapshots (built from rosters + depth charts by `build_sim_team`) and returns a
  `GameResult` with a play log. Same inputs → same game. No DB access in `app/sim/`.
- **Play-level:** each snap is resolved from the two calls (`playcalls.AICoach`; the
  `Coach` protocol is the Coach Mode seam), named plays from the playbooks
  (`playbook.py`), and the specific players' matchups (`resolve.py`). Probabilities are `sigmoid(base + k · rating_difference)`.
- **Events are the contract:** every play records semantic events (handoff, rush, pass,
  sack, tackle, penalty, kicks…). Play-by-play text (`text.py`) and box scores
  (`stats.py`) are derived from events only, and the 3D client animates from them —
  the engine never computes player positions.
- **Penalties** (`penalties.py`): fourteen fouls, each with a base rate in `tuning.py`
  scaled by the awareness of the players who could commit it. Pre-snap fouls replace the
  snap; live ones are called only when the other side would accept them, and enforced as
  a replayed down (offense), an automatic first down (defense), yards added to a play
  that stands (personal fouls) or a lost down (grounding).
- **Fatigue** (`fatigue.py`): each team's energy by player lives on its `SimTeam` for the
  game. Personnel comes from `fatigue.take` (the depth chart's healthy players who aren't
  resting, as tired copies with lower physical ratings); snaps cost energy, the sideline
  and breaks restore it. No random draws.
- **Calibration:** all constants live in `tuning.py`; `calibration.py` measures league
  output against targets, and `tests/test_sim_calibration.py` enforces them plus rating
  sensitivity (+5 OVR ≈ 70% wins). A full 272-game season simulates in ~2 s.

### 3D game client

- R3F scene graph: stadium, 22 player figures (procedural low-poly, per the playback
  design), ball, cameras.
- Animation driven by a timeline choreographed from the engine's play record (playback,
  not client-side physics), so a play always looks the same and ends where the record says.
- Built (M4): the stadium, players, choreographer for every play type, and the Watch page
  with broadcast sideline, end zone and all-22 cameras, follow-ball, and scrubbing.
- Later: per-player state machines from playbook assignments (M5), richer camera rigs and
  instant replay (M6).
- **The Unity viewer** (M9, `unity/`, `docs/unity.md`): a second renderer for the Watch
  page, picked with its Renderer switch when the WebGL build is installed
  (`frontend/public/unity/`). The page keeps the choreographer, clock, director and camera
  (`cameraFollow.ts`, shared with the three.js rig) and sends Unity each play's timeline
  and each frame's time and camera; Unity samples the timeline itself (`TimelineSampler.cs`,
  checked against fixtures the frontend writes). It falls back to the classic viewer if
  Unity can't start.

### Deployment

Docker images for the API (also the worker) and the web app (Next.js standalone), built
and smoke-tested in CI, run on Render: a public web service, a private API, a worker and
managed Postgres per environment (`render.yaml`), staging from `main` and production after
approval (`.github/workflows/deploy.yml`). Logs are JSON lines with request ids
(`app/observability.py`), errors go to Sentry, `/api/ready` gates deploys, and a scheduled
workflow checks uptime. Runbook: [`docs/deploy.md`](docs/deploy.md).

### Later concerns

League-wide export, stats tables (game_player_stats), records.
