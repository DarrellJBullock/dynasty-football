# Design: Living Players and Storylines (Milestone 15)

**Status:** Accepted 2026-10-13 (all §6 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Two things that make a league feel lived in:

- **Living players.** Players with a personality and a mood: they care about playing
  time, winning and their next contract; some ask for a trade or hold out; a locker room
  pulls together or apart; veterans bring rookies along. Each feeds what the game already
  does (development, contracts, free agency, the lineup) by a readable amount.
- **Storylines.** A league that talks about itself: a weekly news feed written from what
  happened (streaks, upsets, milestones, record chases, injuries, trades, firings),
  rivalries that build over the years, and questions from the press after your games,
  whose answers move your players and fans.

### Non-goals for Milestone 15

- Changing how plays resolve: mood and chemistry act between games (development,
  contracts, availability) or as small rating adjustments made before a game, never on
  the engine's random draws; no `SIM_VERSION` bump.
- Real players' or teams' names, quotes or likenesses; generated text stays fictional and
  pronoun-neutral (as commentary is).
- Talking to players one by one, or a dialogue system: personalities show in what players
  do and what the news says.

## 2. What exists

- **Players:** ratings, potential, a development trait, age and contract; injuries; no
  personality or mood.
- **Development** (`domain/development.py`): each offseason, growth toward potential and
  decline with age, scaled by coaches and facilities.
- **Contracts:** re-signing (`services/contracts.py`): a player asks his market price
  (`asking`) and says yes or no to an offer; free agency (`domain/free_agency.py`): a
  player takes the best bid by money, with a pull toward strong teams (`WINNER_PULL`).
- **What's written for people:** play-by-play commentary (`lib/commentary.ts`, from play
  events, deterministic and pronoun-neutral), notifications, the offseason recap, the
  League log, the owner's review.
- **Owners and fans** (Milestone 14): fan mood and owner confidence, with what moved them.

## 3. Living players

- **Personality** (decision 1): every player gets two traits, made once with their own
  random stream (as owners and staff are, so the default league stays byte-identical):
  - **Drive:** *competitor* (wants to win), *mercenary* (wants to be paid), *loyal* (wants
    to stay), *steady* (wants nothing in particular).
  - **Temperament:** *leader*, *team player*, *volatile*.
- **Mood** (0–100, decision 2): moves each week with playing time (a starter, a backup who
  should start), the team's record, the contract (underpaid against his market price, a
  contract year), and how the team treats its players (a trade request granted or
  ignored, the coach's answers to the press). Everything that moves it is shown on the
  player's page, as the owner's confidence is.
- **What mood does** (each a tuning constant, readable on the page):
  - **Development:** a happy player grows a little more; an unhappy one, a little less.
  - **Contracts:** a happy player gives a hometown discount when re-signing; an unhappy
    one asks more, and a *loyal* one rarely tests the market.
  - **Free agency:** *competitors* lean further toward winning teams, *mercenaries* toward
    money; a player who left unhappy won't come back to his old team.
  - **Trade requests:** a very unhappy player asks to be traded; the request is news, and
    his mood falls further each week it's ignored.
  - **Holdouts** (decision 3): an unhappy star in the last year of his deal may hold out
    of the preseason and the opening weeks (he's unavailable, as an injured player is)
    until he's paid or traded.
- **Chemistry** (decision 4): a team's chemistry (0–100) comes from its players' moods
  and temperaments (*leaders* lift it, *volatile* players swing it) and from how long its
  starters have played together. It adjusts the team's ratings a little before each game
  (up to ±1.5 overall points), the way fatigue does: no new draws.
- **Mentoring:** a *leader* veteran at a position helps that position's young players
  develop a little faster.
- **AI teams** manage moods as their direction says: contenders pay their stars, and
  rebuilders trade the unhappy veterans.

## 4. Storylines

- **The news feed** (decision 5): after each week (and each offseason step), the league's
  stories, written from what happened. Each is deterministic (phrasings chosen from the
  league, week and story), pronoun-neutral, and links to the game, player or team:
  - streaks (a winning or losing run), upsets (by the teams' ratings), comebacks;
  - milestones (a player's career yards, touchdowns, sacks; a coach's wins);
  - record chases (a season record within reach, then broken);
  - big injuries, holdouts, trade requests, trades (with the AI's reasons), firings,
    owners' reviews, Hall of Fame classes.
- **What you see:** a News page (the whole league, newest first), the top stories on the
  Dashboard, and your own team's stories in the inbox (decision 6).
- **Rivalries** (decision 7): a rivalry score for every pair of teams, built over the
  years from division games, playoff meetings, close games and upsets (and fading
  slowly). Rivalry games are billed in the news and on the schedule, they move fans more,
  and the broadcast mentions them.
- **The press** (decision 8): after each of your games, one question from the press,
  chosen from what happened (a big win, a bad loss, a player's slump, a rival). You pick
  one of three answers: *confident*, *measured* or *fiery*. Each moves your players' moods
  (and the player named), your fans, and sometimes the next opponent, a little, and the
  answer can make the news. Unanswered, the coach says something measured.

## 5. Testing

- **Living players:** personalities made once and deterministically (the default league
  unchanged); mood moving with playing time, record, contract and treatment; each effect
  (development, re-signing price, free-agency pull, trade requests, holdouts) by its
  constant; chemistry from moods and temperaments, and its rating adjustment; mentoring;
  AI teams managing moods; the calibration and the pinned games unchanged.
- **Storylines:** each kind of story detected from a played week and written
  deterministically and pronoun-neutrally (every phrasing checked, as commentary's are);
  rivalries building and fading; press questions chosen from the game, each answer's
  effects; the News page, the Dashboard's top stories, the inbox; Playwright: a week
  played, the news and a press answer.

## 6. Decisions

1. **Personality:** **two traits, drive and temperament** (recommended; enough to tell
   players apart, few enough to read); or **one trait**; or **five or more traits**.
2. **Mood:** **one number with what moved it shown** (recommended; like owner confidence);
   or **several moods** (about money, playing time, the team).
3. **Holdouts:** **unhappy stars in a contract year may hold out of the preseason and the
   opening weeks** (recommended; real stakes, rare); or **no holdouts**; or **holdouts at
   any time**.
4. **Chemistry:** **a small rating adjustment before each game (up to ±1.5)**
   (recommended; it matters without dominating); or **only affects mood and development**;
   or **a bigger effect**.
5. **The news:** **written from play and league events, deterministic, after each week and
   offseason step** (recommended); or **only for your team**; or **an AI-written feed**
   (not reproducible, and costs per league).
6. **Where the news goes:** **a News page, the Dashboard's top stories, and your team's
   stories in the inbox** (recommended); or **the News page only**.
7. **Rivalries:** **built from history (division, playoffs, close games, upsets) and
   fading slowly** (recommended); or **fixed by division**; or **none**.
8. **The press:** **one question after each of your games, three answers, small effects**
   (recommended); or **a weekly press conference with several questions**; or **none**.

## 7. Delivery plan (separate PRs, each with tests)

1. **Personalities and mood:** traits for every player, mood and what moves it, the
   player page's mood panel, the team's mood at a glance.
2. **What mood does:** development, re-signing, free agency, trade requests, holdouts,
   mentoring; AI teams managing moods.
3. **Chemistry:** from moods, temperaments and time together; its pre-game rating
   adjustment; shown on the depth chart and Dashboard.
4. **The news feed and rivalries:** stories from each week and offseason step, the News
   page, the Dashboard and inbox; rivalry scores and rivalry games.
5. **The press:** questions after your games, answers and their effects, in the news.
