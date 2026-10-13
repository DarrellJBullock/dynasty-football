# Design: Head-to-Head and Commissioner Tools (Milestone 13)

**Status:** Accepted 2026-10-13 (all §6 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Two things leagues with friends (Milestone 11) are missing:

- **Head-to-head games:** when two managers' teams meet, both can coach the same game,
  calling their own side's plays, instead of the game being simulated from both game
  plans.
- **Commissioner tools:** the commissioner can fix what goes wrong and set the league's
  rules: edit any player or team, reverse a trade, roll back a week, and change roster,
  cap and playoff rules.

### Non-goals for Milestone 13

- Voice or video, or chat inside a game (managers can use their own).
- Anything that changes how plays resolve: a head-to-head game is the same engine, with
  a person's calls on both sides instead of one.
- Spectators coaching, or more than two coaches in a game.

## 2. What exists

- **Coach Mode** (`sim/coaching.py`, `services/coach.py`): a coached game is the engine
  replayed from the kickoff with the user's calls so far. `ScriptedCoach` answers each
  snap for one side from the recorded calls (and raises `NeedCall` when it runs out); the
  AI calls for the other side. The engine is deterministic, so every replay reaches the
  same point; `SIM_VERSION` guards against engine changes under a game in progress.
- **Games between two managers** are simulated from both teams' game plans (M11), and
  Coach Mode refuses them.
- **The commissioner** (M11) runs the season (advance, sims, settings, members), can act
  for any team, and can veto trades in the review window.
- **Rules are fixed in code:** a 53-man roster (`domain/positions.ROSTER_MAX`), the
  league's salary cap (its own, but never changed after creation), the playoff format
  (seeds per conference from the league's size).

## 3. Head-to-head games

- **Who:** a game between two members' teams can be **played head-to-head** when both
  managers agree (decision 1); otherwise it's simulated from both game plans, as now.
- **Calls:** each snap, **both coaches call at once** (decision 2): the offense its play,
  the defense its call, each blind to the other's. When both have called, the snap
  resolves and both see it. Kickoffs and conversions are the kicking side's call.
- **Audibles:** at the line, the offense and then the defense may audible, each seeing
  what they'd see on the field (`engine.at_the_line`), as in Coach Mode.
- **Pace** (decision 3): no play clock by default, so a game can be played over an
  evening or over days. Optionally a per-call clock (say, 2 minutes); a coach who runs
  out has the AI call that snap from their game plan. Either coach can hand the rest of a
  drive or the game to the AI, as in Coach Mode.
- **Both pages update:** each coach polls the game (as the inbox does); a notification
  says when it's your call.
- **The engine:** `replay` takes scripted calls for both sides; `NeedCall` says which
  side (or both) must call. A head-to-head game is a coached game with two scripts, so it
  replays, settles and is watched like any coached game.
- **Deadline** (decision 4): if a head-to-head game isn't finished when the commissioner
  advances the week, the AI finishes it from both game plans (its calls so far stand).

## 4. Commissioner tools

- **Edit anything** (decision 5): any player's ratings, position, age, contract and
  team, and any team's identity, roster and depth chart, with an audit entry for each
  change.
- **Reverse a trade:** within the same season, as long as everyone in it is still on the
  team they went to (otherwise refused, with why).
- **Roll back a week** (decision 6): undo the last simulated week (or playoff round):
  its games, stats, injuries, awards and notifications go; rosters stay as they are now.
- **League rules** (decision 7), changed between seasons (in the offseason) so a season is
  never played under two sets of rules:
  - roster size (45-60, default 53);
  - the salary cap, and its growth each season;
  - playoff teams per conference (and byes);
  - regular-season length (for the next season's schedule).
- **The audit log:** every commissioner action (edits, reversals, rollbacks, rule
  changes, vetoes) is listed on a new League log page for every member to see (decision
  8).

## 5. Testing

- **Head-to-head:** both sides scripted reproduce the same game; a snap waits for both
  calls; blind calls (neither sees the other's before the snap); audibles for both sides;
  the per-call clock and the AI stepping in; handing a drive to the AI; the deadline;
  agreement before a game; two browsers playing a short game (Playwright).
- **Commissioner tools:** each edit (and its audit entry); a trade reversed, and refused
  once someone moved; a week rolled back (games, stats, standings, injuries, awards) and
  played again identically; rules changed only in the offseason and applied (roster
  limits, cap, playoff seeds, schedule length); only commissioners; the League log.

## 6. Decisions

1. **When is a game head-to-head?** **When both managers agree, game by game**
   (recommended; an "Offer to play it live" each week); or **always, in a league that
   turns it on**; or **only in the playoffs**.
2. **How do coaches call?** **Both at once, blind, each snap** (recommended; like the real
   game, and neither waits on seeing the other's call); or **offense first, then the
   defense sees the formation** (more information for the defense than real football
   gives).
3. **Pace:** **no clock by default, an optional per-call clock with the AI stepping in**
   (recommended); or **a clock always** (games finish, but friends in different time
   zones struggle); or **real time only** (both online).
4. **An unfinished game when the week advances:** **the AI finishes it from both game
   plans** (recommended); or **the week can't advance until it's done** (one absent
   manager holds up the league).
5. **Editing anything:** **commissioners edit any player and team, with an audit trail**
   (recommended); or **only fixing mistakes** (a narrower set: contracts and rosters).
6. **Rolling back:** **the last week (or playoff round) only** (recommended; simple and
   safe); or **any number of weeks** (powerful, but long rollbacks get confusing); or
   **none**.
7. **Rules changes:** **between seasons only** (recommended); or **any time** (a season
   could be played under two sets of rules).
8. **The audit log:** **visible to every member** (recommended; trust in a league among
   friends); or **commissioners only**.

## 7. Delivery plan (separate PRs, each with tests)

1. **Head-to-head in the engine:** two scripted sides, `NeedCall` for either or both,
   blind calls per snap, audibles for both; the same game from the same calls.
2. **Playing head-to-head:** agreeing to play live, the shared coached game, polling and
   "your call" notifications, the per-call clock and AI stepping in, the week's deadline,
   the Coach Mode screen for two coaches.
3. **Commissioner edits and the audit log:** edit any player and team, every
   commissioner action logged, the League log page.
4. **Reversing trades and rolling back a week.**
5. **League rules:** roster size, cap and its growth, playoff format, season length,
   changed between seasons.
