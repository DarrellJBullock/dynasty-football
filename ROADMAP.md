# Roadmap

Each milestone ends with working software, green tests, and updated docs.

## ✅ M0 — Foundation (complete)

- Monorepo: Next.js 16 frontend, FastAPI backend, PostgreSQL 17, Alembic.
- Initial schema: leagues, conferences, divisions, teams, players, player_ratings,
  contracts, seasons, games, franchises.
- Deterministic fictional league: 32 teams, 1,696 rostered players + 64 free agents,
  contracts under the cap, 17-week schedule.
- Domain rules: 24 attributes, position-weighted OVR, salary valuation, roster template.
- Franchise dashboard: team identity, ratings, cap, roster, next game, top players,
  unit strength, division standings, front-office alerts, schedule, 3D field preview.
- Roster management: filter/sort/search, player card, edit bio & ratings, release,
  sign free agents, create custom players.
- League page: standings by division, power rankings.
- Tests: 60 backend (SQLite + PostgreSQL), 45 frontend.

## M1 — Rosters & customization

- [x] Depth chart editor (drag-and-drop + keyboard), drives team ratings; cross-listing,
      injured starters skipped, per-slot and full reset
- [x] Roster import: CSV, Excel (.xlsx), JSON — per-row validation, preview, add or
      replace modes, skip-invalid option, downloadable templates
- [x] Roster export (CSV, Excel, JSON) in the import format; exports re-import unchanged
- [x] Custom teams (name, city, colours) and custom leagues (4–40 teams, 1–4 conferences
      × 1–4 divisions, cap, season length, generated or empty rosters)
- [x] New-franchise flow: create a league, pick your team; switch between saved franchises
- [x] Playwright end-to-end tests (17 real-browser flows, run in CI)

## M2 — Quick Sim & season

- [x] Play-level simulation engine (deterministic, seeded, calibrated) — design:
      `docs/design/simulation-engine.md`
- [x] Simulate next week / rest of the regular season; stored box scores and play logs
- [x] League leaders (11 categories), player pages with season totals and game logs,
      sortable team season stats
- [x] Schedule page, game page (line score, team stats, box score, scoring summary,
      play-by-play), live records and recent results on the dashboard
- [x] Playoffs and championship: seeding with tiebreakers, reseeded bracket, neutral-site
      final, champion; the season moves to the offseason

## M3 — Franchise management

- [x] Year rollover: offseason → next season, with an offseason recap on the dashboard
      (then free agency and the draft)
- [x] Re-signing with negotiation (Contracts page; asking price by rating, position, age,
      and preferred length; counter-offers; next season's cap)
- [x] Cuts with dead money (signing bonuses on every deal above the minimum; releases,
      trades, and mid-deal retirements accelerate the rest onto the cap)
- [x] Free agency period with AI bidding (five market days; offers, counts, leading/outbid;
      players hold out early and lean toward contenders)
- [x] Draft: generated classes, scouting fog and reports, draft order, draft day with AI
      picks, rookie scale, undrafted free agents, cut-downs
- [x] Trades with AI valuation (players and next year's picks, trade meter, deadline)
- [x] Player development, aging, retirement
- [x] Injuries from simulated games (injury report, recovery countdown, game-page list)
- [x] Records and history (season archive, MVP and player/rookie of the year awards,
      single-season and career records, player career pages)

## M4 — 3D engine foundation

- [x] Play event contract (typed events shared backend ↔ frontend, each play's 22 players in
      the play log, playback API) — design: `docs/design/play-playback.md`
- [x] Stadium, field, and lighting (canvas-painted field, goal posts, stands and crowd,
      light towers, line overlays; camera presets: overview, sideline, end zone, all-22)
- [x] Player models + core animations (procedural low-poly figures sized by build, home and
      away uniforms with numbers; stance, run/carry cycle, block, throw, catch, dive, down,
      celebrate; formations for every defensive package)
- [x] Timeline playback of a single play (a choreographer scripts all 22 players and the
      ball for every play type from the play record — runs, passes, sacks, scrambles,
      kneels, penalties, kickoffs, punts, field goals, conversions; the Watch page at
      `/games/[id]/watch` with play/pause, a scrubber marked with moments, speed,
      previous/next, "play the drive", and sideline/end-zone/all-22 cameras that follow
      the ball)

## M5 — Gameplay

- [x] Offensive & defensive playbooks (25 named plays, 11 defensive calls; the AI calls
      them; concepts fare better or worse against each coverage shell; names in the
      play-by-play and the Watch page) — design: `docs/design/coach-mode.md`
- [ ] Play-call UI
- [x] AI players: routes, blocking assignments, pursuit, coverage (each named play's
      formation, routes and run scheme — pulling guards, pitches, play-action fakes,
      boots, screens — and each defensive call's zones, man matchups and blitzers, drawn
      in 3D)
- [x] Special teams: onside kicks and squibs (engine, AI, play-by-play, 3D); in Coach Mode
      the kickoff (deep, squib, onside) and the conversion (extra point or two) are yours;
      4th down (go, punt, field goal) is a playbook call
- [x] Coach Mode engine and API (a coached game is replayed from the user's calls; start,
      call, timeouts, "let the AI call" a play / drive / game; week-simulation rules)
- [x] Coach Mode UI (Play Game in the sidebar and Coach this game on the Dashboard; the
      call screen with the score bug, situation, playbook tabs, the AI's pick, personnel,
      timeouts and "let the AI call"; each call's plays in 3D, skippable; the final)
- [x] Watch Mode (Watch on every played game in the Schedule; the Watch page plays a game
      straight through, or just its highlights: scores, turnovers, 20-yard plays, missed
      kicks)

## M6 — Broadcast presentation

- [x] Broadcast camera rigs, all-22, end zone (a Broadcast director, the default camera,
      cuts between wide, sideline, tight, end-zone shots by play type and moment; skycam
      and reverse angles; the presets stay one click away)
- [ ] Instant replay with scrubbing
- [x] Score bug and banners (team colors, scores, timeouts, possession, a running game
      clock and the play clock, down and distance; FIRST DOWN, TOUCHDOWN, SACK, FLAG and
      kick banners) on the Watch page and Coach Mode — design: `docs/design/broadcast.md`
- [ ] Stat overlays (player stat lines, drive summaries, halftime and final cards)

## M7 — Platform

- [ ] Accounts and multiple franchise saves
- [ ] Background workers for long sims
- [ ] Deployment pipeline, monitoring
- [ ] Performance & accessibility pass
