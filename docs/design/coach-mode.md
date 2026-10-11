# Design: Gameplay and Coach Mode (Milestone 5)

**Status:** Accepted 2026-10-11 (all §11 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Let the user **coach their team's game**: call every play, watch it unfold in 3D, and live
with the result in the standings, stats and history, exactly as if the game had been
simulated. Along the way, give plays real names and shapes: a playbook on each side of
the ball, players who run the called routes, block the called scheme and play the called
coverage, and the special-teams decisions a head coach makes.

### Non-goals for Milestone 5

- Controlling a player (a joystick/arcade mode). The user is the head coach; the AI
  players execute.
- Custom or editable playbooks, formations and audibles (later, if ever).
- Broadcast presentation: camera rigs, instant replay and overlays are Milestone 6.
- Multiplayer: both sides human. The design allows it, but there's one user today.

## 2. What exists

- **The `Coach` seam.** The engine asks a coach for each offensive and defensive call
  (`app/sim/playcalls.py`); every game today uses `AICoach` for both sides.
- **Determinism.** A game is a pure function of the two rosters, its seed and its calls.
  The same inputs always give the same game.
- **Calls are coarse.** Offense: run inside/outside, pass screen/short/medium/deep with or
  without play action, punt, field goal, kneel. Defense: base/nickel/dime, man/zone,
  blitz or not. Matchups between the specific players involved decide each play.
- **3D playback** (Milestone 4) turns any play record into an animated play. Routes,
  coverage and blocking are chosen by the choreographer at random, constrained by the
  record.

## 3. How a coached game runs

The engine plays a game from kickoff to final whistle in one call. A human coach needs
it to stop and wait at each snap.

**Proposal: replay from the recorded calls.** A coached game stores only the user's calls
so far. Each request replays the engine from the kickoff with those calls (a
`ScriptedCoach` answers from the list) until the coach is asked for a call it doesn't
have; the engine stops there and reports the situation. The user's call is appended, and
the next request replays one play further. Because the engine is deterministic, every
replay reaches the same point, the AI's calls and every random draw included.

- No engine rewrite and no serialized engine state: the stored game is a few hundred
  bytes of calls. It survives server restarts, and the finished game is simply the
  replay of all the calls: stored, box-scored and counted exactly like a simulated game.
- Cost: replaying ~150 plays takes ~30 ms in Python, well inside a request.
  (*Measured:* ~9 ms for a full game.)
- *As built* (`app/sim/coaching.py`): the engine gives a `huddle` to any coach that wants
  one at the start of each snap, before timeouts and the clock runoff, so the user sees
  the true pre-snap clock and can call a timeout with the play. A call stays with its
  snap if the period ends before it; possession changing at the half voids it. Both
  teams are snapshotted at the start (`teams.team_to_dict`), so roster moves mid-game
  don't change the replay. **Engine changes that alter the order of random draws change
  how an in-progress coached game replays**, so ship them with a `SIM_VERSION` bump and
  expect in-progress coached games to be restarted. A game whose calls no longer fit
  the engine is refused with a clear message (409), and `DELETE /api/games/{id}/coach`
  abandons it.
- *Special teams (as built):* the engine asks the kicking team's coach for the kickoff
  (`kickoff_call`: normal, squib, onside) and the scoring team's for the conversion
  (`conversion_call`: kick, two). They're decisions between snaps, recorded in order
  with the user's plays (roles `kickoff` and `conversion`).
- The user can hand any snap, the rest of the drive, or the rest of the game to the AI.

## 4. Playbooks

Named plays, grouped the way a coach thinks of them, each a concrete shape that the
engine resolves and the 3D client draws.

- **Offense** (~24 plays): runs (Inside Zone, Power, Counter, Outside Zone, Toss, Draw,
  QB Sneak), quick passes (Slants, Stick, Hitches), intermediate (Curl-Flat, Smash,
  Flood, Mesh, Dig), deep (Four Verticals, Post-Wheel), play action (PA Boot, PA Post),
  screens (RB Screen, WR Bubble), and Kneel / Spike.
- **Defense** (~12 calls): fronts and shells (Cover 0, 1, 2, 3, 4, Tampa 2, 2-Man),
  pressures (Fire Zone, Edge Blitz, Mike Blitz), and goal-line / prevent.
- Each play maps onto the engine's existing call dimensions (run direction, pass depth,
  play action, package, coverage, blitz) plus a **concept**, and lists every player's
  assignment: routes by role, run-blocking scheme, coverage zones and man matchups, rush
  lanes.
- **Concepts matter, a little.** A small concept-versus-coverage table nudges the
  matchups: Smash is good against Cover 2, slants beat soft zones, blitzes punish long
  developing passes, screens punish blitzes. Every nudge is a constant in `tuning.py`,
  and the AI calls named plays from the same playbooks, so calibration (scoring, yards,
  completion rate, sack rate) stays where it is.

## 5. The AI players (choreography from assignments)

The choreographer stops improvising and draws the called play: receivers run the play's
routes (the target's route still fitted to the recorded air yards), linemen block the
scheme (zone steps, a pulling guard on Power and Counter), defenders play the called
coverage (zone landmarks for the shell, man matchups, the blitzers' paths), and everyone
pursues the ball after the catch or handoff. Old games without named plays keep today's
behavior.

## 6. Coach Mode

- **Where:** your team's next game gets a **Play** button on the Dashboard and Schedule,
  and the sidebar's "Play Game" goes live. Simulating the week first plays your game
  with the AI unless you've started coaching it. A game in progress must be finished (or
  handed to the AI) before the week can be simulated.
- **The call screen:** the score bug, down and distance, field position, clock and
  timeouts; the playbook (offense when you have the ball, defense when you don't) with
  the AI's suggested call highlighted; your recent calls and their results.
- **After each call:** the play runs in 3D on the same screen (the Milestone 4 scene),
  with the play-by-play line, then returns to the call screen. Plays can be skipped to
  just the result.
- **Clock management:** timeouts are yours to call; hurry-up and kneel-downs are
  playbook calls.
- **Finish:** the final whistle goes to the box score, and the week can be simulated.

## 7. Special teams

Coach Mode makes the head coach's kicking decisions. On 4th down: go for it, punt, or
kick a field goal. After a touchdown: kick the extra point or go for two. On kickoffs:
a normal kick, a squib, or an onside kick. Onside kicks are new to the engine (a
recovery chance from the kicker and both teams' hands ratings, a new event and play-log
text) and the AI uses them when trailing late. The 3D scenes for the new kicks come with
them.

## 8. Watch Mode

Any played game can already be watched from its box score (Milestone 4). Milestone 5
adds **Watch** buttons on the Schedule for every final game and a **continuous mode** on
the Watch page that plays the whole game, play after play, with a short pause between.
Live broadcast presentation is Milestone 6.

## 9. Testing

- **Engine:** a coached game replayed from its calls equals the same game simulated with
  those calls; partial replays stop at the right snap; handing a game to the AI finishes
  it; calibration stays green with named plays and concept nudges.
- **API:** start, call, hand off, and finish; refuse calls out of turn or illegal for the
  situation (a punt on 1st down is fine, a field goal from your own 10 is allowed but a
  spike with the clock stopped isn't); simulate-week rules around a game in progress.
- **Frontend:** the call screen, playbook filtering, the play-then-call loop (scene
  mocked); Playwright coaches a few plays, hands the rest to the AI, and lands on the box
  score.
- **3D:** choreography invariants hold for every named play, plus each play's routes and
  coverage shapes.

## 10. Delivery plan (separate PRs, each with tests)

1. **Playbooks:** named offensive and defensive plays as data, concepts in the engine
   with tuned nudges, the AI calling named plays, play names in the play log and the
   play-by-play.
2. **Choreography from assignments:** routes, run schemes, coverage shells and blitzes
   drawn from the called plays.
3. **Coach Mode engine and API:** coached games stored as calls, replay to the next
   decision, call / timeout / hand-off endpoints, week-simulation rules.
4. **Coach Mode UI:** the call screen, the 3D play after each call, Play buttons, the
   sidebar's Play Game.
5. **Special teams:** 4th-down, two-point and kickoff choices in Coach Mode; onside kicks
   and squibs in the engine and in 3D.
6. **Watch Mode:** Watch on the Schedule, continuous play on the Watch page.

## 11. Decisions

Each item lists the recommended option first.

1. **How a coached game runs:** **replay from the recorded calls** (recommended: no
   engine rewrite, survives restarts, the finished game is identical to a simulated one),
   or a **live in-memory session** per game (simpler requests, but lost on restart and
   harder to test), or a **resumable engine** that serializes its state (most work).
2. **Which side you call:** **both** (recommended: the GAME_DESIGN promise, "call every
   offensive and defensive play"), with "let the AI call" always one click away; or
   **offense only**, with the AI on defense.
3. **Do play concepts change outcomes?** **Yes, with small tuned nudges** (recommended: a
   call should matter, and calibration keeps the league believable); or **names only**
   (plays look different but resolve like today's calls); or a **new resolution model**
   built around concepts (much bigger, re-calibrate everything).
4. **Watching each play:** **3D after every call, skippable** (recommended: it's what
   Milestone 4 was for); or **text first**, with 3D as an option.
5. **Week simulation with an unplayed coached game:** **the AI plays it unless you've
   started**; a started game blocks the week until finished or handed off
   (recommended); or **always block** until the user plays or explicitly sims it.
6. **Special teams scope:** **decisions plus onside kicks and squibs** (recommended); or
   **decisions only** (no engine change; onside kicks later).
