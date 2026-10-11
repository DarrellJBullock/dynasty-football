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
- [ ] Cuts with dead money (signing bonuses)
- [x] Free agency period with AI bidding (five market days; offers, counts, leading/outbid;
      players hold out early and lean toward contenders)
- [x] Draft: generated classes, scouting fog and reports, draft order, draft day with AI
      picks, rookie scale, undrafted free agents, cut-downs
- [x] Trades with AI valuation (players and next year's picks, trade meter, deadline)
- [x] Player development, aging, retirement
- [x] Injuries from simulated games (injury report, recovery countdown, game-page list)
- [ ] Records and history (season archives, awards)

## M4 — 3D engine foundation

- [ ] Engine event timeline schema (shared backend ↔ frontend)
- [ ] Stadium, field, and lighting
- [ ] Player models + core animations (stance, run, block, throw, catch, tackle)
- [ ] Timeline playback of a single play

## M5 — Gameplay

- [ ] Offensive & defensive playbooks and play-call UI
- [ ] AI players: routes, blocking assignments, pursuit, coverage
- [ ] Special teams: field goals, punts, kickoffs
- [ ] Coach Mode (call plays, AI executes) and Watch Mode

## M6 — Broadcast presentation

- [ ] Broadcast camera rigs, all-22, end zone
- [ ] Instant replay with scrubbing
- [ ] Score bug, down & distance, stat overlays

## M7 — Platform

- [ ] Accounts and multiple franchise saves
- [ ] Background workers for long sims
- [ ] Deployment pipeline, monitoring
- [ ] Performance & accessibility pass
