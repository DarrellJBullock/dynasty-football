# Design: Depth of Play and Unity (Milestone 9)

**Status:** Accepted 2026-10-12 (all §7 recommendations adopted) · **Author:** Claude Code

## 1. Goal

Two things. First, make **depth matter on the field**: players **tire** over a drive and
recover on the sideline, so backups rotate in and a deep roster plays better late in a
game. Stamina (one of the 24 attributes) finally does something. Second, **render the 3D
game in Unity**: real character models, animation and lighting, in the same Watch and
Coach Mode pages, from the same play records, with the current viewer kept as a fallback.

Plus two small follow-ups: split the backend CI job (25 of its 30 minutes) and show the
week an injured player is expected back.

### Non-goals for Milestone 9

- A native (desktop or mobile) app. The Unity viewer runs in the browser (WebGL), inside
  the existing site; see decision 1. A native app could come later and would need token
  sign-in.
- Changing how plays are decided by anything other than fatigue. Unity draws plays; it
  never decides them (the engine stays the single source of truth, as in Milestone 4).
- Fatigue carried from game to game (a short week, a bye week's rest). Every game starts
  fresh.
- Multiplayer, commentary, crowd sound, a play designer.

## 2. What exists

- **No fatigue.** Every starter plays every snap at full ratings. The only rotation is
  random: the second running back gets about 30% of snaps and each defensive lineman is
  swapped out about 25% of the time (`resolve.offense_personnel` / `defense_personnel`).
  `stamina` is generated, shown and stored, but the engine never reads it.
- **Who was on the field** is recorded on every scrimmage play (`personnel`, since
  `SIM_VERSION` 1.2), but snap counts aren't shown anywhere.
- **The 3D viewer** is React Three Fiber in the browser. The engine records *what*
  happened; `choreograph.ts` (about 1,400 lines, plus tests) turns each play into a
  **timeline**: every player's path and poses over time, the ball's segments (held,
  flight, rest), moments (snap, throw, tackle, flag) and the flag's spot. The scene
  (`PlayScene.tsx`) samples that timeline each frame; the playhead, the camera director,
  instant replay and the HTML broadcast overlay (score bug, banners, lower thirds) all
  live in React around it. Players are simple figures built from boxes and cylinders.
- **No Unity, .NET or Unity license** on this machine or in CI.

## 3. Fatigue and substitutions

- **Energy:** each player has energy from 100 (fresh) down, for the game only.
  - **Each snap on the field costs** a base by position (most for defensive linemen,
    running backs and receivers on deep routes; least for quarterbacks, centers and
    kickers), more on long plays, scaled by stamina: `cost × (1.6 − stamina / 100)`, so
    a 90-stamina player tires at about 70% of the rate of a 60.
  - **Recovery:** a share per snap off the field, more between possessions and at
    timeouts, and most at halftime. Constants go in `tuning.py`.
- **Effect:** a tired player's speed, acceleration, agility and strength drop with his
  energy (about 1 point for every 4 below 100), and his injury odds rise a little.
  Ratings are read through a helper, so resolvers don't change.
- **Substitutions replace the random rotation.** Before each snap, a starter below his
  position's sub-out line (say 70) is replaced by the next healthy player on the depth
  chart who is fresher, and returns once back above the sub-in line (say 88). Positions
  that rotate: RB, WR, TE, DE, DT, OLB, MLB, CB, S. Quarterbacks, offensive linemen and
  kickers don't rotate for fatigue (as in real football). Thin depth means tired starters
  play on.
- **Rotation in the game plan:** a new tendency, **Rotation** (−2 to +2), moves the
  sub-out line: a team that rotates heavily stays fresher but plays its backups more.
  Generated plans lean on depth (a deep defensive line rotates more).
- **Snap counts:** a new `snaps` stat for every player, derived from the recorded
  personnel (events stay the only source of stats). Box scores, player game logs and
  season totals show it.
- **Coach Mode:** the call screen shows the energy of the players on the field for both
  sides (a small bar beside each), and the user's subs follow the same rules.
- **Engine version:** the random rotation's draws go away and fatigue adds none, so the
  order of draws changes: `SIM_VERSION` 1.8. Coached games in progress on 1.7 are
  offered to be abandoned, as before. `NEUTRAL_GAME` is re-pinned; a neutral plan still
  means "the AI as before plans" for calls.
- **Calibration:** today's targets must stay green; the +5 OVR win rate (65–75%) is
  re-checked, since depth now counts.
- **As built** (`app/sim/fatigue.py`, constants in `tuning.py`):
  - Costs per snap: RB 7, DT 7, DE 6.5, OLB 3.5, WR and TE 2.6, MLB 2.4, CB 2.2, safeties
    about 2, linemen 0.8, QB 0.6. Recovery: 5 a snap off the field, 8 a change of
    possession or a quarter break, 4 a timeout, 60 at halftime and before overtime.
    Sub out below 72 (±4 per Rotation level), back at 90. A point off speed,
    acceleration, agility and strength for every 4 of energy lost; injury odds ×(1 + 0.5
    × the share lost).
  - Measured over 150 games: RB1 plays about 75% of snaps and RB2 24%; starting
    defensive linemen 72–78%, with the third and fourth men splitting the rest; the
    quarterback and the line play every snap. The calibration targets, home field and
    rating sensitivity are unchanged and green; injuries are 2.7 a game (2.6 before).
  - Snap counts are a `player_game_stats.snaps` column (migration 0022), so every player
    who took a snap now has a stat line (linemen included). The game page lists them in
    a collapsible "Snap counts" table with each player's share of his unit's snaps.
  - A pre-snap foul uses the same fatigued lineup but costs nobody energy.

## 4. Unity

### 4.1 Shape

- **A WebGL renderer inside the site.** On the Watch page and in Coach Mode, a
  **Renderer** setting chooses **Classic** (today's viewer) or **Unity**. The Unity build
  loads only when chosen; if it fails to load (no WebGL 2, low memory, a blocked
  download), the page falls back to Classic and says so.
- **React keeps everything except the drawing.** The timeline is still built by
  `choreograph.ts` in the browser and handed to Unity whole, through Unity's JavaScript
  bridge. The playhead, the director's camera cues, instant replay and the HTML overlay
  stay in React. Unity receives:
  - `LoadPlay(timeline, teams)`: the play's timeline and both teams' colors, numbers and
    names;
  - `SetTime(seconds)` every frame, and `SetCamera(shot or preset, focus)` when the
    director cuts;
  - and it reports `Ready` and `Error` back.
  One copy of the choreography means the two renderers can't disagree about a play.
- **Code:** a Unity project in `unity/` (C#), pinned to one Unity 6 LTS version. Its job
  is small and testable: sample the timeline (the same rules as `timeline.ts`), drive
  animated characters along their paths and poses, fly the ball, and run the camera
  shots. A shared set of sample timelines (JSON fixtures exported from the TypeScript
  tests) checks that Unity samples the same positions as `timeline.ts`.

### 4.2 Art

- **Players:** one rigged, animated athlete model with a uniform tinted from each team's
  colors, numbers on the jersey, and the existing poses mapped to animations (stance,
  run, block, throw, catch, tackle, celebrate). Height and weight scale the model.
- **Stadium:** the field with team end zones and midfield logo text, lines, goalposts,
  stands and lights; day and night lighting.
- **Sources:** only assets whose license allows shipping them in a public web build:
  Unity's own samples, CC0 packs, or assets you buy. Everything stays fictional: no real
  team marks.

### 4.3 Build, delivery and tests

- **Builds in CI** with GameCI (a Unity build container). It needs a Unity license in
  GitHub secrets (`UNITY_LICENSE`, `UNITY_EMAIL`, `UNITY_PASSWORD`). The WebGL build is
  compressed (Brotli), copied into the web image under `/unity/`, and never committed.
  Target: under 25 MB downloaded, cached after the first load.
- **Tests:**
  - Unity Test Framework edit-mode tests for timeline sampling against the shared
    fixtures, run by GameCI.
  - Vitest for the bridge and the renderer switch, with Unity mocked.
  - Playwright loads the Unity renderer on the Watch page, waits for `Ready`, plays a
    play, and checks it reports the same playhead; and checks the fallback to Classic.

### 4.3a As built (part 3, the foundation)

- Unity 6000.6.5f1, Built-in render pipeline, packages trimmed to the test framework,
  Newtonsoft JSON and the few modules used. The stage (field, end zones in the home
  color, yard lines, the line of scrimmage and line to gain, light) and the play (capsule
  figures in the uniforms' jersey colors with a facing marker, tipping over to lie; the
  ball; the flag) are built in code; the only assets are two materials and an empty scene.
- The page sends the camera itself (`cameraFollow.ts`, shared with the three.js rig), so
  presets, following the ball, the director's cuts and replays look the same in both.
- Build: Gzip with the loader's decompression fallback (no server headers needed), about
  7.7 MB in all; `build.json` names the files. The web image now copies `public/`.
- Tests: 7 edit-mode tests (the sampler against 3 shared fixtures, a run, a pass and a
  punt; messages; coordinates), Vitest for the bridge, the camera and the Renderer switch,
  and `e2e/unity.spec.ts` (loads, plays, next play, remembered, back to Classic) in
  headless Chromium.

### 4.3b As built (part 4, art and cameras)

- **Athletes:** no downloaded models (free asset packs would need a license review and a
  download you approve). Instead Unity builds the classic viewer's own jointed figure
  (PlayerFigure.tsx) part for part: helmet and facemask, pads, jersey with numbers on the
  chest and back (TextMesh), pants, socks, shoes and gloves, sized from height and weight,
  with the classic skin tones. `Poses.cs` ports poses.ts, so stances, the run cycle by
  distance, blocks, throws, catches, dives, tackles, kicks and celebrations match. The
  shared fixtures now check all 13 joint angles and the hip height of every player at
  every sample.
- **Stadium:** the page paints the field exactly as the classic viewer does
  (fieldTexture.ts: stripes, numbers, hashes, team end zones and the midfield logo) and
  sends it as an image once per game; Unity builds the goalposts, four banks of stands
  with ~4,900 fans (one vertex-colored mesh, about half in the home colors), light towers
  with glowing lamps, and lighting matched to the browser's by eye.
- **Coordinates:** everything but the camera hangs from one root mirrored in z, so it is
  placed in the browser's scene coordinates number for number; where three.js combines
  two rotation axes, Unity's are applied in its order (X then Y).
- **Cameras and replays:** already the page's (part 3): the director, presets, follow-ball
  and instant replays drive Unity's camera exactly as the classic one.
- The build stays about 7 MB.

### 4.3c As built (part 5, Coach Mode and the parity check)

- **Coach Mode:** the reel after each call has the Renderer switch too (the choice is
  shared with the Watch page, `field/unity/renderer.tsx`).
- **One Unity for the page:** starting Unity takes seconds and Coach Mode shows a new reel
  after every call, so the page keeps one Unity running (`leaseUnity` in lib/unity.ts):
  each viewer borrows its canvas while shown; between viewers it's parked out of sight and
  idle (a new `SetActive` message turns its camera off and drops it to 2 frames a second).
  Each game's field is sent once. A failed start isn't kept, so the next viewer retries.
- **Parity check** (Chromium, headless; the same play and moment in both renderers, 45%
  and 92% of the way through): run, completion, incompletion, interception, sack, fumble,
  rushing and passing touchdowns, punt, kickoff, field goal, extra point, two-point try,
  kneel, a pre-snap foul and a flag during a play. Framing, players, poses, end zones,
  banners and the overlay match in all 16; Unity's turf reads a little lighter, and it
  draws soft shadows under the players (the classic viewer has none).
- **Performance:** in the same headless browser (software rendering, so a comparison, not
  a benchmark) both ran at the same frame rate (7.3 vs 7.4 a second); the build is about
  7 MB, cached after the first load. A real-GPU check on a mid-range laptop is still worth
  doing before making Unity the default.
- **Accessibility:** axe (WCAG 2.2 AA) finds nothing serious on the Watch page with Unity
  drawing; the canvas keeps its accessible name and the overlay stays HTML.
- **The default:** Classic stays the default (decision 5): switching is your call.

### 4.4 What you need to do

I can't install Unity, create a Unity ID or accept its license for you. Before the Unity
parts can be built and checked:

1. ~~Install Unity Hub and Unity 6 with WebGL Build Support, and sign in~~ (done:
   6000.6.5f1).
2. Add the license secrets for GameCI to the GitHub repository (`docs/unity.md`); until
   then CI skips the Unity job and the deployed site has no Unity renderer.
3. Approve any paid assets, if you want better than the free ones.

## 5. Small follow-ups

- **CI split:** the backend job runs PostgreSQL and SQLite tests one after the other.
  They become two parallel jobs (lint and migrations stay with the Postgres one).
- **Expected return:** "Knee sprain · Out 2 games · back week 9" on the injury report,
  the roster and the player page, from the season's current week. Playoff rounds count as
  weeks; season-ending injuries say "Out for the season".

## 6. Testing

- **Fatigue:** energy costs by position and stamina, recovery off the field and between
  possessions, the subs (out below the line, back above it, only fresher backups, never
  QBs or linemen, thin depth plays on), the Rotation tendency, tired players' ratings and
  injury odds, snap counts matching the personnel, the box score and player pages,
  Coach Mode's energy bars, calibration and rating sensitivity, the 1.7 → 1.8 coached-game
  handling.
- **Unity:** as in §4.3.
- **Follow-ups:** the expected-return wording; CI is checked by running it.

## 7. Decisions

1. **Unity's shape:** a **WebGL renderer inside the site**, with Classic kept as the
   default until Unity matches it and as the fallback (recommended); or **replace the
   current viewer** outright; or a **native app** (desktop or mobile) as a second client,
   which needs token sign-in, its own screens and store releases.
2. **Where the choreography lives:** **keep it in TypeScript and hand Unity the finished
   timeline** through the JavaScript bridge (recommended: one copy, nothing to port); or
   **port it to C#** (two copies to keep in step); or **move it to the game server**
   (needed only for a native app).
3. **Who runs the playhead and cameras:** **React** (the clock, the director, replays and
   the overlay), with Unity only drawing (recommended); or **Unity runs everything** inside
   its canvas, with the overlay rebuilt in Unity.
4. **Art:** **free, permissively licensed assets** to start (recommended); or **paid
   Asset Store packs** you approve; or **commissioned models** (most work and cost).
5. **When Unity becomes the default:** **after a parity check** (every play kind,
   cameras, replays, performance on a mid-range laptop), by your call (recommended); or
   **from the first release**.
6. **Fatigue's subs:** **automatic by thresholds, tuned by a Rotation tendency in the
   game plan** (recommended); or **automatic only**; or **per-position rotation settings
   on the depth chart** (more control, more UI).
7. **Fatigue across games:** **every game starts fresh** (recommended); or **carry some
   fatigue over** short weeks and rest it on byes (more to explain and calibrate).
8. **Coached games across the engine change:** **bump `SIM_VERSION` to 1.8 and offer to
   abandon a 1.7 game in progress**, as before (recommended).

## 8. Delivery plan (separate PRs, each with tests)

1. **Follow-ups:** the CI split and the expected-return week.
2. **Fatigue and substitutions:** energy, subs, the Rotation tendency, snap counts, Coach
   Mode's energy bars (`SIM_VERSION` 1.8).
3. **Unity foundation** (needs §4.4): the `unity/` project, the bridge, the Renderer
   switch and fallback, timeline sampling with the shared fixtures, simple models, and the
   CI build into the web image.
4. **Unity art and cameras:** the athlete model and animations, uniforms, the stadium and
   lighting, the broadcast cameras and replays.
5. **Unity in Coach Mode and the parity check:** the renderer in Coach Mode, performance
   and accessibility (the canvas keeps its label; the overlay stays HTML), then the
   default decision (decision 5).
