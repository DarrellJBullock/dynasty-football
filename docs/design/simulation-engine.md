# Design: Game Simulation Engine (Milestone 2)

**Status:** Accepted 2026-10-10 (all §11 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Simulate football games from team ratings and depth charts, fast enough to play a full
season in seconds and detailed enough to produce real box scores, player stats, and a
play-by-play log. The same engine must later drive **Coach Mode** (the user calls
plays) and the **3D game** (M4–M6), so a watched game and a simulated game agree.

### Non-goals for Milestone 2

- Player-position physics or per-frame movement (the 3D client derives motion later; §8).
- Injuries, fatigue-driven substitutions, and development (Milestone 3; hooks only).
  *Update (M3): in-game injuries now exist — see `app/sim/injuries.py`, `SIM_VERSION`
  1.1, and GAME_DESIGN.md "Injuries".*
- A user-facing play-calling UI (Coach Mode is Milestone 5; the interface is designed now).

## 2. Recommendation: play-level resolution

| Option | How it works | Supports | Verdict |
|---|---|---|---|
| **Score-only** | Sample a final score from team OVRs | Standings | Too thin: no stats, nothing to watch |
| **Drive-level** | Each drive ends in TD / FG / punt / turnover by probability | Standings, team stats | No player stats, no play calling, nothing for 3D |
| **Play-level** ✅ | Each snap is resolved from the two play calls and the players involved | Everything: player stats, play-by-play, Coach Mode, 3D playback | Recommended |
| Agent physics | Simulate all 22 players' movement every tick | Everything, most "real" | Far too slow and hard to calibrate for Quick Sim |

Play-level is the sweet spot: about 130 snaps per game × 272 games ≈ **35,000 plays per
season**. At a target of ≤ 0.2 ms per play in pure Python, a full season simulates in
under 10 seconds and a single week in under 1 second.

Each play is resolved by **matchups** between the specific players involved, not by
team OVR. For example, the left tackle's pass blocking against the right end's pass rush
decides pressure, and the targeted receiver against the covering corner decides
openness. That is what makes the depth chart, injuries, and roster moves matter.

## 3. Architecture

```
backend/app/sim/                pure Python, no database, no HTTP
  state.py       GameState: quarter, clock, possession, down, distance, ball spot, score, timeouts
  teams.py       SimTeam: players by depth-chart slot plus ratings, built from the DB once per game
  playcalls.py   PlayCall / DefenseCall types; situational AI for both sides
  playbook.py    named offensive plays and defensive calls (M5), concept-vs-shell edges
  resolve/       run.py, pass_.py, special.py (one resolver per play family)
  clock.py       time elapsed per play, two-minute and kneel-down logic
  engine.py      simulate_game(home, away, seed, *, coaches) -> GameResult
  stats.py       fold play results into player and team box scores
  calibration.py league-wide targets plus a harness to check them
```

```
           ┌────────── per snap ──────────┐
GameState ─►  offense coach  → PlayCall    │
           │  defense coach  → DefenseCall │
           │  resolver(rng)  → PlayResult  ├─► events, yards, clock, turnover…
           └──────────────────────────────┘
                     │ apply
                     ▼
           GameState' … until the game ends → GameResult (score, plays, box score)
```

- **Coaches are an interface.** `Coach.call(state, team) -> PlayCall`. Milestone 2 ships
  `AICoach`; Coach Mode later plugs in a `HumanCoach` that waits for the user. Both
  sides use the same rules.
- **The engine is pure.** Inputs are two `SimTeam` snapshots, an RNG seed, and the
  coaches. The output is a `GameResult`. No database access inside `app/sim/`, matching
  how `app/domain/` works today.
- **Determinism.** Each game's seed is `hash(league_id, season_year, week, game_id)`, and
  every random draw goes through that game's own `random.Random`. The same inputs give
  the same game, which makes results reproducible, testable, and replayable.

## 4. Play calling (AI)

**Offense** chooses by situation:

| Situation | Call tendencies |
|---|---|
| Normal downs | Run/pass mix by down and distance (≈ 45/55 on 1st and 10), shifted by the team's relative run and pass strength |
| 3rd/4th and long | Pass, mostly medium or deep |
| Short yardage, goal line | Run inside, quarterback sneak, play-action |
| 4th down | Punt / field goal / go, using a field-position × distance × score table |
| Two-minute drill | Pass, sideline routes, spike; no-huddle clock |
| Protecting a lead late | Run, then kneel to end the game |

Pass calls carry a target **depth** (screen, short, medium, deep) and a **read order**.
The QB doesn't "choose" a receiver up front; see §5.2.

**Defense** chooses a **personnel package** (base, nickel, dime, goal line), a
**coverage** (man or zone), and a **blitz rate** by situation. Blitzing raises pressure
odds but leaves coverage thinner.

*Update (M5, `SIM_VERSION` 1.3):* every call is now a **named play** from the playbooks in
`app/sim/playbook.py` (see docs/design/coach-mode.md §4). The AI makes the coarse choice
above, then picks a named play that matches it (an inside run becomes Inside Zone, Power,
Counter or Draw; man coverage with a blitz becomes Cover 0 or a Mike Blitz). A pass play's
target weights set the QB's progression, and he favors his first two reads
(`Tuning.read_bonus`); a screen's designed target is open by design (`screen_open`). Each
concept gains or loses a little against each coverage shell (`Tuning.concept_edges`),
centered against the AI's shell mix so a play called at random breaks even.

## 5. Play resolution

Probabilities use a logistic curve over **rating differences**, so the advantage between
two players is what matters, not their absolute numbers:

```
p = sigmoid(base + k · (offense_rating − defense_rating) / 10)
```

`base` and `k` are calibration constants (§7). Yardage uses skewed distributions with a
long-gain tail, since football yards are not normally distributed.

### 5.1 Run

1. **Blocking at the line:** average of the 5 OL plus TE/FB `run_blocking` and `strength`
   at the point of attack, against DL/LB `block_shedding`, `strength`, and
   `play_recognition`. The result is a *push* score.
2. **Ball carrier:** `ball_carrier_vision`, `elusiveness`, `speed`, and `acceleration`
   against the tacklers' `tackling` and `speed`.
3. **Yards:** base yards drawn from the push score plus noise, with a breakaway chance
   (an exponential tail) driven by speed and elusiveness versus pursuit.
4. **Fumble:** a small chance from `carrying` against the tackler's `tackling` and
   `strength`.

### 5.2 Pass

1. **Protection:** each OL `pass_blocking` against the rushers' `pass_rush` (more rushers
   when blitzing). This sets the time the QB has before pressure, and the chance of
   a sack or a hurried throw.
2. **Read:** the QB checks receivers in read order. Each receiver's *openness* comes from
   `route_running`, `speed`, and `agility` against the covering defender's
   `man_coverage` or `zone_coverage` and `play_recognition`. QB `awareness` decides how
   many reads the QB gets through before throwing or taking a sack.
3. **Throw:** completion chance from `throw_accuracy` (and `throw_power` for deep balls),
   target depth, openness, pressure, and the receiver's `catching`. Each pass ends as
   **complete**, **incomplete**, **interception** (rising with tight coverage, depth, and
   pressure), or **defended**.
4. **Yards after catch:** the receiver's `elusiveness` and `speed` against the nearest
   defender's `tackling`.

### 5.3 Special teams

- **Field goals / PATs:** make chance from distance, `kick_power`, and `kick_accuracy`. The
  coach won't try one beyond the kicker's effective range.
- **Punts:** distance from `kick_power` with noise; fair catch, touchback, or a simple return.
- **Kickoffs:** mostly touchbacks; otherwise a simple return.

### 5.4 Penalties

v1 included three common, outcome-relevant ones at flat rates: **false start**,
**offensive holding**, and **defensive pass interference**. Since `SIM_VERSION` 1.7
(`penalties.py`; docs/design/dynasty-mode.md §6) there are fourteen, with rates scaled by
the awareness of the players involved, calibrated to about six accepted flags and 50
yards a team a game.

### 5.5 Clock

Each play consumes realistic time: about 38 s for a run that stays in bounds with the clock
running, about 6 s for an incompletion, plus huddle time. Includes the two-minute warning,
3 timeouts per half used by the AI, and kneel-downs.

## 6. Output: play log and events

Each snap produces a `PlayResult`:

```json
{
  "n": 42, "q": 2, "clock": "4:12", "off": "HFD",
  "down": 3, "dist": 7, "spot": 64,
  "call": {"type": "pass", "depth": "medium", "coverage": "zone", "blitz": false},
  "result": {"type": "complete", "yards": 14, "first_down": true, "td": false},
  "events": [
    {"t": "snap"},
    {"t": "pressure", "by": 3412},
    {"t": "throw", "qb": 3521, "target": 3530, "air": 11},
    {"t": "catch", "player": 3530},
    {"t": "tackle", "by": [3477], "yac": 3}
  ],
  "text": "Quarles pass short right to Draper for 14 yards (Whitlock). First down."
}
```

- **The play-by-play text** is generated from the events.
- **Box scores and stats** are folded from the events, so the log and stats can't disagree.
- **The 3D client** (M4) plays the same events back: it builds formations and motion from
  them. Events are the contract between the engine and the renderer, which means the
  engine never computes positions. This **revises** ARCHITECTURE.md, which mentions
  "per-player positions over time"; semantic events keep the engine fast and leave
  animation to the renderer.
- Logs carry a `sim_version`, so old games stay valid and replayable after the engine changes.
- *Update (M4, SIM_VERSION 1.2): scrimmage plays also record `personnel` — the 22 players
  on the field and the defensive package — and kicks name a `returner`, for 3D playback
  (`docs/design/play-playback.md`). Neither draws random numbers, so outcomes are unchanged.*

## 7. Calibration

Ratings must produce realistic football, with fictional teams but believable numbers.
`sim/calibration.py` simulates a seeded league season and checks league averages
against targets:

| Metric (per team, per game) | Target range |
|---|---|
| Points | 20–25 |
| Plays from scrimmage | 60–68 |
| Completion % | 60–67% |
| Yards per pass attempt | 6.3–7.5 |
| Yards per carry | 4.0–4.6 |
| Sacks allowed | 1.8–2.8 |
| Interception rate | 1.8–2.8% of attempts |
| Fumbles lost | 0.4–0.8 |
| Field goal % | 82–90% |
| Punts | 3.5–5.0 |
| Ties | < 1% of games |
| Accepted penalties (since 1.7) | 5–7 |
| Penalty yards (since 1.7) | 40–60 |

**Rating sensitivity:** the better team should win more often, but not always.

| Matchup (team OVR) | Expected favorite win rate |
|---|---|
| Equal | ~50% (home ~57%) |
| +5 OVR | 65–75% |
| +10 OVR | 80–90% |

These tables become **automated tests** that run a few hundred seeded games. Any engine
change that drifts the game out of range fails CI.

## 8. Persistence and API

**Schema** (one migration):
- `games`: add `seed`, `sim_version`, `play_log` (JSON; about 30 KB per game, about 8 MB per
  season, fine for Postgres JSONB), and `overtime`.
- `player_game_stats`: one row per player per game, with passing, rushing, receiving,
  defense, and kicking columns. Season totals and league leaders aggregate it in SQL.
- `team_game_stats`: first downs, total yards, turnovers, time of possession, and
  penalties per team per game.

**Season flow:** `preseason` → `regular_season` → `playoffs` → `offseason`, with
`seasons.current_week` advancing as weeks are simulated.

**Endpoints:**

| Method & path | Purpose |
|---|---|
| `POST /api/seasons/{id}/simulate` `{ "until": "next_week" \| "end_of_regular_season" \| "end_of_playoffs" }` | Simulate games in order and update standings |
| `GET /api/leagues/{id}/schedule?week=` | Week view with scores |
| `GET /api/games/{id}` | Box score, team stats, scoring summary, play-by-play |
| `GET /api/leagues/{id}/leaders?stat=` | League leaders |
| `GET /api/players/{id}/stats` | Game log and season totals |

Simulation runs **synchronously** at first. One week takes about 1 s, a full season
under 10 s, with a progress UI. If real timings exceed budget, it moves to a background
job with polling. That is the M7 job-queue item, pulled forward only if needed.

**Lineups:** each team plays its **depth chart** (Milestone 1). Out/IR players are
skipped, using the same `starting_lineup` rules the team ratings use, plus backups by
depth order for substitutions.

## 9. Playoffs

- **Default league:** 7 teams per conference (4 division winners and 3 wild cards);
  the top seed gets a bye. Single elimination, then a championship game at a neutral site.
- **Custom leagues:** seeds per conference = the largest of 2, 4, 6, or 7 that is at most
  half the conference's teams, with byes filling out the bracket. Leagues with one
  conference use one bracket.
- **Tiebreakers:** win %, head-to-head, division record, conference record, point
  differential, then a seeded coin flip.

## 10. Delivery plan (separate PRs, each with tests)

1. **Engine core:** `app/sim/` with state, AI coaches, run/pass/special-teams resolvers,
   clock, events, and play-by-play text. Calibration and sensitivity tests. No database,
   no UI.
2. **Season simulation:** migration, simulate endpoint, stats persistence, standings from
   results, a **Schedule** page, and a **Game** page (box score and play-by-play). The
   dashboard shows real records and the next game.
3. **Stats:** league leaders, player game logs and season stats, team stats.
4. **Playoffs and championship:** seeding, bracket page, champion banner, season moves
   to the offseason. Rolling over to the next season is Milestone 3.

## 11. Decisions (resolved)

All six were resolved with the recommended option, listed first in each item.

1. **Resolution level:** play-level (recommended, §2) or drive-level (faster to build,
   but no player stats, play calling, or 3D path).
2. **Overtime:** regular season uses one 10-minute period where both teams get the ball
   unless the first drive scores a TD, and ties are possible; playoffs continue until
   there's a winner (recommended). Or skip overtime and allow ties.
3. **Penalties in v1:** the three described in §5.4 (recommended), or none until later.
4. **Home-field advantage:** about +1.5 points of expected margin (recommended, matching
   modern football), or none.
5. **Custom-league playoffs:** the automatic seeding rule in §9 (recommended), or a
   per-league playoff-size setting in the league builder (more control, more UI).
6. **Fatigue in v1:** simple rotation only (RBs and DL rotate by snap share; recommended),
   or real stamina modeling now (more realistic, more calibration work).
