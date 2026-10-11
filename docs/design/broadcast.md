# Design: Broadcast Presentation (Milestone 6)

**Status:** Accepted 2026-10-11 (all §8 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Make a game in 3D look like a TV broadcast. The camera is directed, cutting to the right
angle for each moment. Big plays get an instant replay. Graphics carry the situation:
a score bug with a running clock, down and distance, banners for first downs and
touchdowns, and stat lines for the players who matter. It applies everywhere plays are
shown in 3D: the Watch page and Coach Mode.

### Non-goals for Milestone 6

- Commentary (text or audio) and crowd sound. (A later, separate idea.)
- Player models, animation, or simulation changes: the plays are the same plays.
- Highlight-reel exports (video files).

## 2. What exists

- **Cameras** (`components/field/layout.ts`, `CameraRig.tsx`): sideline, end zone and
  all-22 presets that the viewer picks by hand. "Follow ball" moves them along the field.
  The rig eases toward each shot, so changes are smooth pans and never cuts.
- **Timelines** carry the play's **moments** (snap, handoff, throw, catch, kick, contact,
  tackle, touchdown, turnover, flag, whistle), every player's path, and the ball. That
  is enough to direct a broadcast without touching the engine.
- **The Watch page** has a play caption, a plain score line, scrubbing, speed,
  straight-through play and highlights (`lib/highlights.ts`). **Coach Mode** shows each
  call's plays in a smaller reel.
- **Stats** are derived from play events (`app/sim/stats.py`). The browser has every
  event of the game in the playback data.

## 3. Graphics (overlays)

HTML over the canvas, not text in the 3D scene: crisp at any size, cheap, accessible to
screen readers, and styled with the app's design tokens.

- **Score bug** along the bottom: both teams in their colors with scores and timeout
  pips, possession, the quarter and the **game clock**, the **down and distance** and
  spot, and the **play clock** before the snap.
  - The game clock **runs during the play**, from the clock at the snap down by the
    play's real time, and stops on incompletions and out-of-bounds plays as the record
    says.
  - The play clock counts down in the pre-snap second.
- **Banners** at the moment they happen: FIRST DOWN, TOUCHDOWN, INTERCEPTION, FUMBLE,
  SACK, FLAG (with the foul), FIELD GOAL GOOD / NO GOOD, ONSIDE RECOVERED.
- **Lower thirds** after notable plays: the player's game stat line so far, e.g.
  "K. Quarles · 18/24, 231 yds, 2 TD". Computed in the browser from the game's events up
  to that play, following the same rules as `stats.py`.
- **Between possessions:** a drive summary ("8 plays · 75 yards · 4:12 · Touchdown").
  At the half and the final whistle: a team stat comparison card.

## 4. The director (camera)

A new **Broadcast** camera, the default, that cuts between angles itself.

- A pure **shot list** per play: `(time, shot)` cues chosen from the timeline's
  moments and the play type. Tested like the choreographer.
  - Pre-snap: the high sideline wide shot.
  - Runs: the sideline tracking the ball, tightening on the carrier.
  - Passes: wide enough to see the receiver at the throw, then follow the catch.
  - Kicks: the end zone behind the kicker for field goals and extra points, a wide
    tracking shot for kickoffs and punts.
  - After the whistle: a close shot on the ball carrier or the tackle.
- **New shots:** tight (on the ball, low and close), skycam (behind and above the
  offense), and reverse angle (from the far sideline, for replays).
- **Cuts are instant.** Moves within a shot ease as today. The manual presets stay, as
  the "pick a camera" option.

## 5. Instant replay

After a highlight play (scores, turnovers, 20-yard plays, missed kicks; the Watch
Mode rule) the broadcast **replays it**.

- The replay uses a different angle (end zone, reverse or skycam, by play type), at
  half speed, with a REPLAY tag and a wipe in and out.
- It starts a beat after the whistle, plays the action (snap to whistle, not the
  pre-snap), then carries on to the next play.
- It's skippable, and can be switched off. On the Watch page, an Instant replays
  setting. In Coach Mode, replays only during a reel of several plays, never while
  you're on the clock.

## 6. Testing

- **Pure modules:**
  - The running game clock and play clock.
  - Banner selection.
  - Stat lines from events, matching `stats.py`'s rules on shared fixtures.
  - Drive summaries.
  - The director's shot list for every play type.
  - Replay selection.
- **Components (Testing Library, scene mocked):** the overlays show and update at the
  right moments; the replay sequence; the settings.
- **Playwright:** the Watch page on Broadcast with the overlays visible, a replay played
  and skipped, Coach Mode's reel with the score bug.

## 7. Delivery plan (separate PRs, each with tests)

1. **Score bug and banners:** the broadcast score bug with the running game clock and
   play clock, down and distance, timeouts and possession; banners at their moments.
   The Watch page and Coach Mode's reel.
2. **The director:** shot lists, new shots, cuts, the Broadcast camera as the default.
3. **Instant replay:** automatic replays of highlights, angle, slow motion, REPLAY tag
   and wipe, settings.
4. **Stat overlays:** player stat lines after notable plays, drive summaries, halftime
   and final cards.

## 8. Decisions

Recommended option first.

1. **Camera:** **an automatic Broadcast director as the new default**, with the manual
   presets still one click away (recommended); or **manual only**, with more presets
   (tight, skycam, reverse) added.
2. **Instant replays:** **automatic after highlight plays**, skippable and switchable
   (recommended); or **on request only** (a Replay button with angle choices); or
   **after every play**.
3. **Graphics:** **HTML overlays on the canvas** (recommended: crisp, accessible,
   cheap); or **graphics in the 3D scene** (on-field text and 3D banners, flashier but
   blurrier and harder to read).
4. **Stat lines:** **computed in the browser from the game's events** (recommended: no
   new API, consistent with "stats come from events"); or **a new API** serving per-play
   running stats.
5. **The game clock:** **runs during each play** (recommended: it's what a broadcast
   shows); or **shows the clock at the snap** only.
6. **Where:** **both the Watch page and Coach Mode** (recommended); or **the Watch page
   only**, leaving Coach Mode's reel plain.
