# Design: Sound (Milestone 10)

**Status:** Accepted 2026-10-12 (all §7 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Make watching and coaching a game *sound* like a broadcast: the crowd, the whistle, the
pads, the kick, and a commentary team calling the play. Everything is timed from what the
viewers already know about each play (its moments and banners), so the sound always
matches what's on screen, in the classic viewer and in Unity alike.

### Non-goals for Milestone 10

- Music (menus, intros), or sound outside the Watch page and Coach Mode.
- Recorded voice actors or a library of real commentary lines.
- Any change to how plays are decided. Sound, like 3D, only presents the play record.
- Sound in Unity itself: the page makes all the sound, for both renderers (decision 3).

## 2. What exists

- **No audio anywhere** in the app.
- **Every play has a timeline** with its moments in seconds: snap, handoff, throw, catch,
  kick, contact, tackle, touchdown, turnover, flag and whistle. The broadcast graphics
  already turn a play into banners (First down, Touchdown, Sack, Interception, Fumble,
  Flag, field goals…), lower thirds and drive summaries, all from the play's events.
- **One clock drives each viewer**: the page's playhead, which plays, pauses, scrubs, runs
  at 0.5×–2×, and replays highlights from a second angle. Both renderers follow it.
- **Browsers block sound until the visitor interacts** with the page (a click or a key).

## 3. Sound effects and the crowd

- **Effects, timed to the play's moments:** the quarterback's cadence and the snap, pads
  and hits on contact and tackles (heavier for sacks and big hits), the thump of a kick and
  the ball off the foot, the whistle at the end of the play, and the referee's whistle and
  a flag on fouls.
- **The crowd:** a bed of stadium noise all game, louder late in close games and in the
  playoffs; it swells as a big play develops and reacts to the result. The home crowd
  cheers home scores, big gains and takeaways, groans at the visitors' and goes quiet; a
  neutral-site game splits the difference.
- **Following the clock:** sounds are scheduled against the playhead, so pausing pauses
  them, scrubbing doesn't replay every sound in between (only the crowd's level follows),
  speed changes keep them in step, and an instant replay is quieter, without the crowd's
  reaction again.
- **How they're made** (decision 1): synthesized in the browser with the Web Audio API
  (noise, filters and envelopes for the crowd, hits and kicks; oscillators for the
  whistle), so there are no audio files to license, download or host. The sound design is
  code and can be tuned.

## 4. Commentary

- **Two voices:** a play-by-play announcer calls what happens ("Quarles back to throw…
  finds Wolfe at the 30… he's down at the 22"), and an analyst adds a line between plays
  when there's something to say: a player's day so far, the drive, the situation (fourth
  down, two-minute drill, a comeback), a streak, fatigue or an injury, a penalty's cost.
- **Written from the events,** like the play-by-play text and the stat overlays, with
  varied phrasings chosen deterministically from the play (the same play is called the
  same way every time it's watched), never real names (the league is fictional).
- **Captions:** each line shows at the bottom of the viewer as it's spoken, so commentary
  is there with the sound off too (and for deaf and hard-of-hearing viewers).
- **Spoken** (decision 2): by the browser's speech synthesis, two voices picked from what
  the visitor's device has, paced to the play (a line that would run past the next moment
  is cut short or skipped). The crowd ducks under the voices.

## 5. Controls

- A **Sound** button and a volume slider on the Watch page and in Coach Mode, with
  separate switches for effects and crowd, and for spoken commentary and captions. The
  choices are remembered in the browser.
- **Off until turned on** (decision 4): the first click on Sound starts the audio (which
  browsers require anyway). `prefers-reduced-motion` doesn't affect sound; a reduced-data
  connection skips nothing (there are no files).
- Coach Mode: sound plays with each reel; the call screen itself is quiet.

### As built (part 1)

- `lib/sound/cues.ts` (pure): a play's cues from its timeline's moments: the snap count
  0.7 s before the snap, the snap, catches, kicks, contact and tackles (a big hit for a
  sack, a takeaway or a loss), flags and the whistle; and the crowd: a swell from the
  handoff or catch to the end of a big play, then a cheer or groan for whoever it was good
  for (scores, takeaways, sacks, stops on downs, gains of 20 and 40 yards, third- and
  fourth-down conversions, kicks made and missed, onside recoveries). The home crowd
  groans at the visitors' good plays; at a neutral site it cheers either way, at half
  volume. Its level: 0.35, +0.2 in a close (8 points or fewer) fourth quarter or
  overtime, +0.15 in the playoffs, at most 0.8.
- `lib/sound/engine.ts`: Web Audio synthesis (seeded noise through filters and envelopes,
  oscillators for the whistle and the snap count), one engine for the page, an always-on
  crowd bed at the situation's level, and `window.dynastySound` (state and the last
  sounds) for tests.
- `lib/sound/useGameSound.ts`: settings (off until turned on; volume, effects, crowd;
  remembered), cues fired as the viewer's playhead passes them (none on a jump of more
  than 0.3 s, so scrubbing is quiet), replays at half volume without the crowd's reaction,
  and the engine suspended when the viewer goes away. The Sound controls sit with the
  viewer's other controls on the Watch page and in Coach Mode's reel.

## 6. Testing

- **Pure, unit-tested:** the sound cues for a play (which sounds, when, how loud) from its
  timeline, banners and situation; the crowd's level over a game; the commentary lines for
  plays and between plays (deterministic, and every event kind has a line); the speech
  pacing (what's cut or skipped).
- **The scheduler:** with the Web Audio API and speech synthesis mocked: play, pause,
  scrub, speed, replays, and switching sound off mid-play.
- **The controls:** Testing Library for the buttons, slider and remembered choices;
  captions appear in time with the playhead.
- **Playwright:** turning sound on starts an audio context (a test hook reports its state
  and the cues scheduled), captions show during a play, and choices survive a reload.
- **Accessibility:** captions are text in the page (an `aria-live` region, polite, that a
  screen reader can follow or the visitor can turn off).

## 7. Decisions

1. **Where the sounds come from:** **synthesized in the browser** (recommended: nothing to
   license or host, small, tunable; less realistic than recordings); or **recorded sound
   effects** from public-domain (CC0) libraries, which I'd need your approval to download
   and which add a few MB; or **a paid sound pack** you buy.
2. **The commentators' voices:** **the browser's built-in speech** (recommended: free,
   works offline, voices vary by device and sound synthetic); or **a cloud voice service**
   (much more natural; costs per character, needs an account and an API key on the game
   server, and lines are generated and cached server-side); or **captions only, no
   speech**.
3. **Where sound plays:** **the page, for both renderers** (recommended: one sound engine,
   in step with the page's clock); or Unity's own audio for the Unity renderer (two
   engines to keep alike).
4. **Default:** **off until the visitor turns it on, remembered** (recommended); or on by
   default (it still can't start until a click).
5. **The crowd's allegiance:** **the home crowd** cheers the home team (recommended, like
   a real broadcast); or a neutral crowd that reacts to big plays either way; or it
   follows your franchise wherever it plays.

## 8. Delivery plan (separate PRs, each with tests)

1. **Sound engine, effects and the crowd:** the Web Audio engine on the page's clock, the
   cues for every kind of play, the crowd's level and reactions, the Sound controls on the
   Watch page and in Coach Mode.
2. **Commentary text and captions:** the play-by-play and analyst lines from the events,
   shown as captions in the viewer.
3. **Spoken commentary:** the voices, pacing against the playhead and replays, the crowd
   ducking under them, and the commentary controls.
