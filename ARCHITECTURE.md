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
and only reaches that user's leagues (`api/access.py`).

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
| `players` | league_id, team_id?, name, position, jersey (0–99), age, height_in, weight_lb, college, years_pro, **overall** (cached), potential, development_trait, injury_status, injury? (description), injury_weeks (games still to miss), retired_year?, is_prospect, scouted, draft_year?, draft_round?, draft_pick? |
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
| `PATCH /api/teams/{id}` | Edit team identity (city, nickname, abbreviation, colors, stadium) |
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
| `POST /api/games/{id}/coach/call` | Make the next call `{play, package?, timeout?}`; the snap is played up to the next call. 422 for a call that doesn't fit the situation |
| `DELETE /api/games/{id}/coach` | Abandon a game in progress (e.g. one coached on an older engine): it can be coached again or simulated |
| `POST /api/games/{id}/coach/auto` | Let the AI call the next play, the rest of the drive, or the rest of the game (`{scope}`) |
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
  `/coach` renders the franchise's next game the same way): each call posts to the coach API,
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
| Injuries | pytest | contact and toughness odds, injury table ranges, injured players sit for the rest of the game, play outcomes unchanged before the first injury, determinism, status mapping, weekly countdown (hand-set statuses untouched), lineups skip the injured, dashboard report, game-page list, manual healing, offseason healing |
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
| Sim ahead | pytest + Vitest + Testing Library + Playwright | several seasons as a job (labels, exact progress, the next preseason, three champions), the franchise on autopilot (re-signs, drafts, cut to 53, under the cap), stopping between weeks and carrying on, 1–10 seasons, params only for sim ahead, the league lock; the Dynasty report (oldest first, the offseason after each season, up to 10 seasons); compaction (which games, the box score page unchanged, nothing to watch, the last two seasons untouched, what a compacted log keeps); the controls (choose seasons, the report link, from free agency, stopped, failed), the report page, History's link, compacted notes; Playwright sims a season ahead and reads the report |
| Performance and accessibility | perf tool + Playwright + Vitest | `app.perf` builds seasons and times every API read (CI: 600 ms and 80 queries per read); LCP under 2.5 s and layout shift under 0.1 on the dashboard, roster, schedule, game and Watch pages; three.js only on pages with a 3D view; axe (WCAG 2.2 AA) on every page, fresh and with a week played, signed in and out, and one `h1` each; a keyboard-only sign-in, skip link and sim; reduced motion (replays start off, the hook follows the system setting) |
| Deployment and monitoring | pytest + Vitest + Playwright + CI | readiness (unmigrated vs current schema), request ids (given or made), each request logged with its route template and user, JSON log lines, Sentry off without a DSN and its scrubbing, email to an outbox or the log, password reset (the emailed link works once, signs out everywhere, expires, the same answer for unknown addresses, a few an hour, removed with the account); the proxy (`/api` to `API_URL` or `API_HOSTPORT` with a request id, sign-in redirects, public pages); the forgot and reset forms; Playwright resets a password from the emailed link; CI builds both images and smoke-tests them together (migrate, API ready, web app up, sign up through the proxy, worker running) |
| Accounts | pytest + Vitest + Testing Library + Playwright | sign up (normalized email, the cookie's flags, rules), sign in and out (the same answer for an unknown account), rate limiting and its window, the first account taking over leagues from before accounts, expired and extended sessions, only token hashes stored, changing the password signing out other browsers, deleting the account and its leagues, the admin reset, the seeded dev account; each account's own leagues and active franchise; **every route with an id answers 404 to another account** (walked from the OpenAPI schema), and the routes without ids are a known list; signed-out visitors get 401; the league limit; changes from other sites refused; the forms (sign in back to `?next=`, errors, sign up to the league builder, safe `next`), the account page and the sidebar menu; Playwright signs out, is sent to sign in, signs up a second account that can't open the first one's games, and signs back in to where it was headed |
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
servers or dev data. CI runs them as a third job and uploads traces on failure.

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

### Deployment

Docker images for the API (also the worker) and the web app (Next.js standalone), built
and smoke-tested in CI, run on Render: a public web service, a private API, a worker and
managed Postgres per environment (`render.yaml`), staging from `main` and production after
approval (`.github/workflows/deploy.yml`). Logs are JSON lines with request ids
(`app/observability.py`), errors go to Sentry, `/api/ready` gates deploys, and a scheduled
workflow checks uptime. Runbook: [`docs/deploy.md`](docs/deploy.md).

### Later concerns

League-wide export, stats tables (game_player_stats), records.
