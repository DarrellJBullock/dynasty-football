# Design: Staff and Legacy (Milestone 12)

**Status:** Accepted 2026-10-13 (all §6 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Two things a decades-long dynasty is missing:

- **A staff to build.** Coaches, a scout and a trainer, with ratings that change how
  players develop, how well you read the draft, and how quickly the injured come back,
  plus facilities to invest in. Another layer of decisions, each one explainable in the UI
  (pillar 3: readable depth).
- **A legacy to look back on.** A Hall of Fame that inducts the league's greats, numbers
  retired by the teams they defined, and record books for each franchise as well as the
  league.

### Non-goals for Milestone 12

- Staff who change how a game is played (see decision 2): play calling stays the AI's and
  the game plan's, so the engine, its calibration and every pinned game stay as they are.
- A money economy (ticket sales, revenue, owners): staff are paid from their own budget
  (decision 3), separate from the player salary cap.
- Real coaches' or players' names, anywhere.

## 2. What exists

- **Development** (`domain/development.py`): each offseason, a player grows toward his
  potential at a rate set by his development trait, holds at his peak, then declines; the
  chance of retiring rises with age.
- **Scouting** (`domain/draft.py`): a prospect's projection is his true rating plus a
  stable error (`scout_noise`, SD fixed); scouting reports (24 per class) reveal the truth.
- **Injuries** (`sim/injuries.py`): who gets hurt and for how many weeks, from the injury
  RNG (separate from the play RNG).
- **History** (`services/history.py`): every season's champion and awards (MVP, OPOY,
  DPOY, OROY, DROY), and league-wide single-season and career records. Retired players
  keep their stats (`players.retired_year`).
- **Jerseys** are assigned from position ranges (`domain/positions.available_jersey`).

## 3. Staff

- **Roles** (decision 1): a **head coach**, an **offensive coordinator**, a **defensive
  coordinator**, a **scout** and a **head trainer**. Each has a name (fictional), an age,
  a 40–99 rating, a specialty where it matters (e.g. the OC's quarterback development),
  a contract (years and salary), and a record (seasons, wins, titles) that follows them
  from team to team.
- **What they do** (off the field only; decision 2):
  - **Development:** the coordinators raise their side's young players' growth rate and
    slow their veterans' decline (the head coach adds a smaller boost to everyone). A
    90-rated OC is worth roughly a development trait step for a young quarterback;
    a 50-rated one is neutral.
  - **Scouting:** the scout shrinks the projection error (`scout_noise`'s SD) and adds
    scouting reports per class.
  - **Injuries:** the trainer shortens injury layoffs (rounded weeks) and, a little, the
    chance of re-injury; facilities add to it.
  - The player page explains each effect ("+12% growth from OC M. Okafor (88)").
- **The staff budget** (decision 3): each team has a staff budget (the commissioner's
  setting, the same for every team) for salaries and facilities. It's separate from the
  player salary cap.
- **The coaching carousel** (decision 4): after the season, staff contracts run out,
  coaches retire, and AI teams fire coaches who lost. The user hires from a market of
  free-agent staff (the AI hires too); a coach can be fired with the rest of his contract
  as dead money against the staff budget.
- **Facilities** (decision 5): a **training facility**, a **medical center** and a
  **scouting department**, each at level 1–5. An upgrade costs staff budget, takes effect
  next season, and adds to the matching staff member's effect. Levels slowly lose value
  unless maintained.
- **Several managers** (M11): each manager runs their own team's staff; AI teams' staff
  are run by the AI. Sim ahead runs the user's staff on autopilot (`autopilot=True`).
- **Determinism:** staff are generated with their own `random.Random` (seeded from the
  league seed), never the league generator's stream, so the default league stays
  byte-identical (`test_womens_leagues.py`). Staff effects scale rates the existing rules
  already draw; they make no new draws inside a game.

## 4. Legacy

- **The Hall of Fame** (decision 6): each offseason, retired players become eligible after
  a waiting period, and the class is chosen by a **legacy score** from their career: stats
  by position (against the league's leaders), awards, championships, seasons as a starter,
  and peak rating. Up to a few players a year are inducted when they pass the bar.
  The Hall of Fame page lists every member with their case ("3× MVP · 2 titles · 41,250
  pass yds"), and shows the candidates who came close.
- **Retired numbers** (decision 7): a team retires the number of a Hall of Famer who
  played most of his career there (AI teams automatically; the user decides for their
  own, at induction or any time after). A retired number is never issued again by that
  team.
- **Record books:** each team's records (single-season, career, single-game), its
  all-time leaders, and its history of seasons, alongside the league's records that exist
  today. The League page and a team page link to them.
- **Coaches' legacy:** head coaches' career records (wins, playoff wins, titles) and a
  Coach of the Year award each season.

## 5. Testing

- **Staff:** generation (deterministic; the default league unchanged), each effect's size
  (development, scouting error and reports, injury weeks), the carousel (contracts ending,
  retirements, AI firings and hirings, the market, dead money), the budget, facilities,
  autopilot, several managers.
- **Legacy:** eligibility and the legacy score (every position can get in), the class each
  offseason, retired numbers (never reissued), team record books, Coach of the Year.
- **The engine is untouched:** calibration and the pinned games stay green with no new
  `SIM_VERSION`.
- **Frontend and Playwright:** the staff page (hire, fire, upgrade), the player page's
  explanations, the Hall of Fame page, a team's record book; a sim ahead long enough to
  induct a class.

## 6. Decisions

1. **Staff roles:** **five: head coach, OC, DC, scout, head trainer** (recommended); or a
   **head coach only** (simpler, less to manage); or a **full staff** (position coaches,
   strength coach, etc.; more to manage than it's worth now).
2. **Do staff affect games?** **No: development, scouting and injuries only**
   (recommended; the engine, its calibration and coached games' replays stay as they are);
   or **yes, coordinators shade play calling** (more flavor, but a new `SIM_VERSION`, new
   calibration and changes to the AI that every game runs through).
3. **Paying staff:** **a separate staff budget, the same for every team** (recommended;
   no economy to build); or **under the player salary cap** (staff compete with players
   for money, which punishes small rosters oddly); or **no cost** (no decisions to make).
4. **Hiring and firing:** **a coaching carousel each offseason, AI teams included**
   (recommended); or **the user's team only** (AI teams' staff never change).
5. **Facilities:** **three facilities, levels 1–5, upgraded from the staff budget**
   (recommended); or **none** in this milestone.
6. **The Hall of Fame:** **automatic, from a legacy score, with the case shown**
   (recommended; deterministic and explainable); or **a vote** (the commissioner, or the
   managers, choose from a ballot each year); or **both** (the score makes the ballot, the
   league votes).
7. **Retired numbers:** **automatic for AI teams, the user's choice for their own**
   (recommended); or **never** (numbers are only ever reissued).
8. **Eligibility:** **3 seasons after retiring** (recommended; dynasty seasons go by
   quickly); or **5** (as in real football).

## 7. Delivery plan (separate PRs, each with tests)

1. **The Hall of Fame and legacy:** eligibility, the legacy score, induction each
   offseason, the Hall of Fame page, retired numbers, and team record books. (Coach of
   the Year needs head coaches, so it comes with part 2.)
2. **Staff:** the staff model and generated staff for every team, ratings and records, the
   staff page (read-only at first), and head coaches' careers and Coach of the Year.
3. **What staff do:** development, scouting and injury effects, explained on the player
   page.
4. **The coaching carousel and budget:** contracts, firing and hiring, the staff market,
   the AI's moves, dead money, autopilot, several managers.
5. **Facilities:** levels, upgrades, upkeep, and their effects.
