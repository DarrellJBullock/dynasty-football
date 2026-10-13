# Design: Owners and Front Offices (Milestone 14)

**Status:** Accepted 2026-10-13 (all §7 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Two things that give a decades-long dynasty pressure from both sides:

- **Owners, money and job security.** Every team has an owner with priorities and
  patience, a market, fans whose mood follows the team, and a season's finances. The
  owner sets goals each season and judges you on them; let them down for long enough and
  you're out of a job, and look for another one.
- **Smarter AI front offices.** AI teams decide whether they're contending or rebuilding
  and build their rosters to match, plan their cap, offer you trades, and trade with each
  other, so the league stays competitive over decades instead of drifting.

### Non-goals for Milestone 14

- Changing how plays resolve: owners, money and AI front offices all act between
  games, so the engine, its calibration and every pinned game stay as they are (no
  `SIM_VERSION` bump).
- A full business simulation (concession prices, parking, sponsorship deals, stadium
  construction).
- Player personalities and morale (a later milestone).
- Real owners', teams' or players' names, anywhere.

## 2. What exists

- **Money:** only the player salary cap (a league rule, which can grow each offseason) and
  the staff budget (salaries, staff dead money and facilities' upkeep, a league setting).
  No revenue, no expenses beyond those, no owners, no fans.
- **The AI front office:**
  - Trades: AI teams only answer. They value players (`domain/trades.player_value`:
    talent, upside, age, contract surplus) and picks, want 5% more than they give, and
    value positions of need more. They never offer a trade, and never trade with each other.
  - Free agency: they chase their top affordable targets, and upgrades over a starter.
  - The draft: they take the best prospect, leaning to positions of need.
  - Re-signing: they keep the young and the good, leaving room under the cap to fill the
    roster.
  - Staff: they fire a head coach after a bad season (the carousel).
- **Leagues with friends:** members run their own teams; anything that skips a member's
  decision takes `autopilot=True` on sim ahead.

## 3. Owners and money

- **Owners:** every team has a fictional owner, made once per league with their own
  `random.Random(f"owners:{league.id}")` (as staff are), never the generator's stream, so
  the default league stays byte-identical. An owner has a **priority** (win now, build
  something lasting, or turn a profit) and **patience** (1–5).
- **Markets and fans:** each team has a market size (small, medium, large) and a fan base.
  **Fan mood** (0–100) rises with winning, playoff runs, star players and cheap tickets,
  and falls with losing and price rises; it fills the stadium.
- **A season's money** (decision 1), worked out after each week and summed for the
  season, every number shown on a Finances page:
  - Revenue: tickets (attendance × price; attendance from fan mood and market), an equal
    share of media money, merchandise (stars and winning), and playoff gates.
  - Expenses: the player payroll and dead money, the staff payroll and facilities.
  - What it's for: the owner's judgment and the fans. The salary cap and the staff budget
    still decide what you can spend; money never stops a signing.
- **Ticket prices** (decision 2): one choice before each season (low, normal, high):
  cheaper tickets fill the stadium and lift fan mood, dearer ones earn more per seat.
- **Owner goals** (decision 5): before each season, 2–3 goals from the owner's priority and
  the team's situation, e.g. "make the playoffs", "win 9 games", "start four players 25 or
  younger", "turn a profit". At the season's end the owner reviews them.
- **Owner confidence** (0–100): moves with the goals met or missed, fan mood and the
  team's direction, more slowly for a patient owner. It's shown on the Dashboard with the
  goals and the last review.

## 4. Job security

- **Getting fired** (decision 3): when confidence falls below a line after a season's
  review, the owner fires the general manager. On by default in a league played alone, off
  by default in a league with friends (a commissioner setting), and a league can turn it
  off entirely.
- **What next** (decision 4): you choose from the open jobs (AI teams whose owners have
  just fired their GM, and any owner who wants you) and take over that team, keeping your
  career record (seasons, wins, titles, firings) across teams. In a league with friends,
  your old team goes to the AI.
- **AI general managers** are judged the same way: an AI GM who's fired is replaced, and
  the team's direction is decided afresh.

## 5. Smarter AI front offices

- **Direction** (decision 6): each offseason, every AI team decides whether it's
  **contending**, **in the middle**, or **rebuilding**, from its roster's strength and age,
  its cap, and its owner's priority. The League page shows each team's direction and why
  ("Rebuilding: the league's third-oldest roster, two starters over 32").
- **Building to match:**
  - Contenders pay for veterans in free agency, trade picks and prospects for help, and
    re-sign their starters.
  - Rebuilders let older veterans walk, sign young players to short deals, trade veterans
    for picks, and draft for potential.
  - Everyone plans the cap a season ahead, keeping room for the extensions they'll want.
- **Trade offers to you** (decision 7): AI teams offer managers trades: a player they need
  for what they can spare, explained ("The Squall are contending and need a cornerback").
  At most one a week per manager, mostly near the deadline and in the offseason, through
  the trade offers members already use (accept, reject, counter, with the AI answering a
  counter at once). An offer expires after three days.
- **AI-to-AI trades** (decision 8): a handful each season, mostly deadline deals between a
  contender and a rebuilder, listed with every other trade on a Transactions list.
- **Determinism:** every AI decision draws from its own `random.Random` keyed by league,
  year and week (as the market and the carousel do), never the game's or the generator's
  streams; members' teams are never decided for, except on autopilot.

## 6. Testing

- **Owners and money:** owners made once and deterministically (the default league's
  fingerprint unchanged); fan mood moving with results and prices; revenue and expenses
  adding up to the season's numbers; goals chosen from priority and situation, and
  reviewed; confidence moving with them, more slowly for patient owners.
- **Job security:** firing below the line (and not when it's off, or in a league with
  friends unless the commissioner allows it); open jobs; taking another team, with the old
  one going to the AI and the career record carried over; AI GMs fired and replaced.
- **AI front offices:** direction chosen from roster, age and cap; contenders and
  rebuilders signing, re-signing, drafting and trading differently; cap room kept for
  extensions; offers to managers (rate, timing, expiry, counters); AI-to-AI trades at the
  deadline; all of it the same for the same league and seed; calibration of league parity
  over 20 simulated seasons (the spread of wins stays within a target range).

## 7. Decisions

1. **What money does:** **feeds the owner's judgment and the fans only; the salary cap and
   staff budget still decide spending** (recommended; readable, and no money death
   spiral); or **the owner funds the staff and facilities from profit** (replacing the
   staff budget); or **a full economy where cash limits signings**.
2. **Ticket prices:** **one choice before each season: low, normal or high** (recommended);
   or **none (set automatically)**; or **a price for each game**.
3. **Getting fired:** **on by default when you play alone; a commissioner setting, off by
   default, with friends; a league can turn it off** (recommended); or **always on**; or
   **never** (owners only comment).
4. **After a firing:** **choose from the open jobs and keep your career record**
   (recommended); or **start a new league**; or **game over** (the league ends).
5. **Owner goals:** **2–3 a season from the owner's priority and the team's situation**
   (recommended); or **one fixed goal (make the playoffs)**; or **you choose your goals**.
6. **AI direction:** **contending, in the middle or rebuilding, chosen each offseason and
   shown with why** (recommended); or **the same, hidden**; or **no direction** (smarter
   rules only).
7. **AI trade offers to managers:** **up to one a week per manager, mostly near the
   deadline and in the offseason** (recommended); or **none**; or **as many as the AI
   likes**.
8. **AI-to-AI trades:** **a handful each season, listed on a Transactions list**
   (recommended); or **none**.

## 8. Delivery plan (separate PRs, each with tests)

1. **Owners and fans:** owners (priority, patience), markets, fan mood, owner goals and
   the season's review, confidence; the Dashboard's owner card.
2. **Money:** revenue and expenses each week and season, ticket prices, the Finances page,
   profit goals.
3. **Job security:** firing, open jobs, taking another team, the career record; AI GMs
   judged and replaced.
4. **AI direction and roster building:** contending, middle, rebuilding; free agency, the
   draft, re-signing and cap planning by direction; shown on the League page.
5. **AI trades:** offers to managers, AI-to-AI deadline deals, the Transactions list,
   parity calibration.
