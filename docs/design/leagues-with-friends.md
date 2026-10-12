# Design: Leagues with Friends (Milestone 11)

**Status:** Accepted 2026-10-12 (all §9 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Play a league with other people: each friend runs a team, a commissioner keeps the
season moving, managers trade with each other, and anyone can follow along with a
read-only link. A league's data can also be exported whole.

### Non-goals for Milestone 11

- Real-time head-to-head play (both coaches calling the same game live); see decision 2.
- Chat, forums, or public league directories (finding strangers to play with).
- Paid features, ads, or anything that needs payments.
- Changing how games are simulated.

## 2. What exists

- **Accounts:** email and password, private leagues. A league belongs to one user
  (`leagues.user_id`), and `api/access.py` answers 404 for anyone else's.
- **One franchise per league** (a unique constraint): the user's team. The rest are AI.
  About 30 places assume "the franchise" is the only human team: the draft auto-picks for
  everyone else, the free-agency market bids for AI teams, trades are always with the AI,
  Coach Mode coaches only the franchise's game, the dashboard and history centre on it,
  and sim ahead runs the franchise on autopilot.
- **Long sims are background jobs** that lock the league against writes while they run.
- **Email** is already sent (password resets) through SMTP when configured.
- Users have an email address but no display name.

## 3. Members, roles and invites

- **Members:** a league has members, each a **commissioner** or a **manager**, and each
  runs at most one team. Teams without a manager stay AI. The league's creator is its
  first commissioner (there can be more than one).
- **Franchises become per member:** the one-franchise-per-league rule becomes one per
  member (league, user), so every manager has their own dashboard, roster and game plan,
  and "the franchise" in today's code becomes "the signed-in member's team".
- **Display names:** users choose a display name (shown to other members instead of their
  email, which stays private).
- **Invites** (decision 6): the commissioner makes an invite link; whoever opens it signs
  in or signs up, then joins and picks one of the open teams (or the commissioner assigns
  one). Links expire and can be revoked. Members can leave; a commissioner can remove a
  manager, whose team goes back to the AI.
- **Who may do what:** managers run their own team (roster, depth chart, game plan,
  contracts, free-agency bids, draft picks, trade offers) and see the whole league;
  commissioners also change league settings, advance the season, run sims, manage
  members, and can act for a team whose manager is away. `api/access.py` grows a member
  check (404 for non-members, as today) and a team check (403 for someone else's team).

## 4. The season together

- **Advancing** (decision 1): the commissioner advances the season (a week, the
  playoffs, each offseason step). Managers mark themselves **ready** for the next week;
  the commissioner sees who's ready and can advance when everyone is, or anyway.
  Optionally, the league advances on a schedule (say, daily at 9 pm) once the deadline
  passes.
- **Games between two managers' teams** (decision 2) are simulated from both teams' game
  plans. Coach Mode is for games against an AI team, as today.
- **The draft** (decision 3) has a pick clock set by the commissioner (from two minutes
  for a live draft night to a day for a slow draft). It's your pick when the clock reaches
  you; when it runs out, the AI picks for you by your needs. AI teams pick at once.
- **Free agency:** each market day, every manager's bids compete with the AI's; the
  commissioner advances the days, as with weeks.
- **Sim ahead** stays single-player: in a league with other managers, the season moves one
  step at a time, by the commissioner.

## 5. Trades between managers

- A manager offers a trade to another manager (players and picks, as today with the AI);
  the other can **accept**, **reject** or **counter**. Offers expire after a few days and
  are withdrawn if a player in them moves. Trades with AI teams work as now.
- **Fairness** (decision 4): optionally, the commissioner reviews trades between managers
  before they go through (a veto window), off by default.

## 6. Notifications

- **An inbox** in the app (decision 5): it's your pick, a trade offer or answer, the week
  advanced, a game result, an invite accepted, a manager is waiting on you. A badge on the
  sidebar counts unread items. Pages refresh when you come back to them (polling; no
  always-open connections).
- **Email**, optional per member and per kind (off by default), through the SMTP the app
  already uses.

## 7. Sharing and export

- **A read-only link** (decision 7): the commissioner can make a public link to the
  league that shows standings, the schedule, box scores, stats, history and the Watch page
  (no rosters' contract details, nothing editable), without an account. It can be
  revoked, and it's never guessable.
- **League export:** the whole league as one JSON file (teams, players and ratings,
  contracts, seasons, results, awards, history), with a documented format; per-team roster
  export (CSV, Excel, JSON) stays as it is. Importing a whole league is later.

## 8. Testing

- **Access:** every route checked for non-members (404), managers acting on another's team
  (403), and commissioners; `test_accounts.py`'s walk over every route grows these.
- **Members and invites:** joining, picking a team, leaving, removal (back to the AI),
  expired and revoked links, display names.
- **The season:** ready check-ins, advancing (and the schedule), games between two
  managers simulated with both plans, the draft clock and auto-pick, free-agency bids from
  several managers, sim ahead refused in multi-manager leagues.
- **Trades:** offers, counters, expiry, invalidation, the veto window.
- **Notifications:** each kind created once for the right people; email off by default.
- **Sharing and export:** the public link shows only what it should and stops working when
  revoked; the export's format.
- **Playwright:** two users in two browser contexts: invite, join, trade, ready and
  advance; the read-only link signed out.

## 9. Decisions

1. **Advancing the season:** **the commissioner, with ready check-ins and an optional
   daily schedule** (recommended); or **automatically when everyone's ready**; or **on a
   fixed schedule only**.
2. **Games between two managers:** **simulated from both game plans** (recommended); or
   **both coach, taking turns** (each side's calls whenever they're next: a game can take
   days); or **one side coaches** (who?).
3. **The draft:** **a pick clock set by the commissioner, with auto-pick when it runs out**
   (recommended); or **live only** (everyone online); or **the commissioner drafts for
   absent managers**.
4. **Trade review:** **none by default, an optional commissioner veto window**
   (recommended); or **always reviewed**; or **never**.
5. **Notifications:** **an in-app inbox, with optional email** (recommended); or **in-app
   only**; or **email only**.
6. **Invites:** **expiring, revocable links** (recommended); or **email invitations to an
   address** (only that person can use it).
7. **Following a league:** **a revocable read-only public link** (recommended); or
   **members only** (followers need an account and an invite).
8. **League size:** **up to every team human, the rest AI** (recommended); or a smaller cap
   (say 12 managers).

## 10. Delivery plan (separate PRs, each with tests)

1. **Members, roles and invites:** the members model, display names, franchises per
   member, invite links, the access checks, and the commissioner's members page.
2. **The season together:** ready check-ins, advancing (and the schedule), the draft clock,
   several managers in free agency, human-vs-human games simulated, sim ahead limits.
3. **Trades between managers:** offers, counters, expiry, the optional veto.
4. **Notifications:** the inbox and optional email.
5. **Sharing and export:** the read-only link and the whole-league export.
