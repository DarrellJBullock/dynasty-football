# Design: 3D Play Playback (Milestone 4)

**Status:** Implemented 2026-10-11 (all §9 recommendations adopted; the four PRs of §8 are
delivered) · **Author:** Claude Code

## 1. Goal

Watch any simulated play in 3D: the 22 players line up, the play unfolds, and the
result matches the box score exactly — same carrier, same yards, same tackler, same
outcome. This is the foundation that Coach Mode and Watch Mode (Milestone 5) and the
broadcast presentation (Milestone 6) build on.

### Non-goals for Milestone 4

- Changing how plays are *decided*. The simulation engine stays the source of truth; 3D
  is a presentation of its results.
- Physics, collisions, or player AI that could change an outcome (Milestone 5 adds
  routes, blocking, and pursuit as smarter *animation*, still bound to the result).
- Broadcast polish: camera rigs, replays, score bug (Milestone 6).
- A native or Unity client. Playback runs in the browser on React Three Fiber, inside the
  existing app (see §9).

## 2. The core problem

The engine records **what** happened, not **where**:

```json
{"t": "dropback", "qb": 3521, "depth": "medium"},
{"t": "pass", "qb": 3521, "target": 3530, "result": "complete", "yards": 14},
{"t": "tackle", "by": [3477]}
```

To show it, something must invent plausible positions over time for all 22 players and
the ball, **constrained** by those events. That is *choreography*.

| Option | How it works | Verdict |
|---|---|---|
| **Choreograph from events** ✅ | A deterministic choreographer turns a play record into a timeline: formation, scripted paths per role, ball flight, all bound to the recorded outcome | Recommended: fast, exact to the box score, no engine changes to outcomes |
| Agent simulation for display | Run a physics/agent sim of all 22 players, nudged toward the result | Hard to guarantee the recorded result (the tackle must happen at the recorded spot); a project of its own |
| Engine computes positions | Make the sim engine track positions every tick | Rejected in the sim design (§2 there): far too slow for Quick Sim |

## 3. The play timeline (the contract)

The choreographer outputs a **timeline**, the only thing the renderer needs. Coordinates
are in yards: `x` runs along the field (0 = one back line, 120 = the other, end zones
included); `y` across it (0–53.3); time `t` in seconds from the snap.

```ts
interface PlayTimeline {
  version: 1;
  duration: number;                 // seconds, snap to whistle
  los: number; firstDownLine: number | null; // field x of the lines to draw
  ball: Keyframe[];                 // includes height (z) for passes and kicks
  players: {
    id: number; side: "offense" | "defense"; role: Role; // "QB", "WR1", "LT", "CB2", ...
    number: number; name: string; team: TeamColors;
    path: Keyframe[];               // position + facing over time
    poses: { t: number; pose: Pose }[]; // stance, run, block, throw, catch, carry, tackle, down
  }[];
  moments: { t: number; kind: "snap" | "handoff" | "throw" | "catch" | "contact" | "tackle" | "touchdown" | "whistle"; text: string }[];
}
interface Keyframe { t: number; x: number; y: number; z?: number; facing?: number }
```

The renderer interpolates keyframes (smoothly, so paths curve) and blends poses. It
never needs to know the rules of football.

*As built* (`frontend/src/components/field/playback/timeline.ts`): facing comes from the
direction of travel unless a pose key pins it; the ball is a list of segments (held by a
player, in flight on an arc, or at rest) rather than keyframes; time starts one second
before the snap so the players are seen set; and a timeline can carry a penalty flag.

### Engine change: who was on the field

Play records name only the players *involved* (carrier, passer, target, tacklers). To
line up all 22 we need the full personnel. **Proposal:** the engine adds
`"personnel": {"offense": [11 ids], "defense": [11 ids], "package": "nickel"}` to each
scrimmage play, and returner ids to kicks (`SIM_VERSION` 1.2). That adds about 15 KB
per game. Older games fall back to each team's current depth chart, marked
"approximate lineup" in the viewer.

## 4. Choreography

A pure, deterministic module (§9 says where) with a script per play type. Any variation
(route stems, which way a run cuts) is seeded by the game's seed and the play number, so
a play always looks the same.

- **Formations:** offense in base 11 personnel (QB, RB, 3 WR, TE, 5 OL), from the
  recorded personnel; defense in base, nickel, or dime from the recorded package. Placed
  at the line of scrimmage, on the hash the previous play ended on.
- **Runs:** handoff at ~0.8 s; the line drives forward and engages the defensive front;
  the carrier's path bends through a gap toward the **recorded gain**; the recorded
  tackler(s) converge and meet him at the end spot at the end time. Long runs get a
  breakaway; fumbles show the ball coming loose and the recovery.
- **Passes:** QB drops back by call depth (screen / short / medium / deep). Receivers run
  routes from a small route tree sized to their depth; the **target's** route is fitted
  so the ball arrives at the recorded air distance. Coverage follows the defensive call
  (man trails, zones sink). Completions: catch, then run after catch to the recorded spot
  and tackler. Incompletions land near the target (broken up if `pass_defended`).
  Interceptions: the defender undercuts and returns the recorded yards. Pressure and
  sacks: the recorded rusher beats his blocker to the QB.
- **Scrambles, kneels, spikes:** simple scripts.
- **Kicks:** kickoffs and punts with hang time, the returner's path to the recorded
  spot, fair catches and touchbacks; field goals and extra points with the ball's flight
  and a make or miss.
- **Penalties:** a flag pose at the whistle; a nullified play still plays out.

**Invariants** (checked by tests for every play type): exactly 22 players at the snap;
everyone stays on the field or crosses the sideline only on out-of-bounds plays; the ball
ends at the recorded spot; the recorded carrier and tackler meet at the end; a touchdown
crosses the goal line; the same play always produces the same timeline.

## 5. The scene

- **Stadium and field** (grows out of today's dashboard preview): turf with yard lines,
  numbers, hash marks, sidelines, end zones painted in the home team's colors with its
  name, goal posts, low-poly stands, and stadium lights. Built from primitives and canvas
  textures: no downloaded assets.
- **Players:** stylized low-poly figures made from primitives (helmet, shoulder pads,
  torso, limbs), in team colors with jersey numbers. **Procedural animation** drives the
  poses: a run cycle whose stride follows speed, plus stance, block, throw, catch, carry,
  dive, and down. No rigging pipeline or animation files, and every player is
  fictional-safe by construction. A glTF character pipeline can replace them later
  without touching the timeline.
- **Cameras:** three presets — broadcast sideline (default), end zone, and all-22 overhead
  — plus "follow the ball". Fuller rigs are Milestone 6.
- **Performance:** about 22 × 10 meshes plus the stadium, instanced where repeated; target
  60 fps on a mid-range laptop. The 3D code loads only when the viewer opens
  (`next/dynamic`, `ssr: false`, as the preview does today).

## 6. The viewer

A **Watch** button on each play in a game's play-by-play opens
`/games/[id]/watch?play=42`:

- Play / pause, a scrubber with the moments marked (snap, throw, catch, tackle), speed
  (0.5× / 1× / 2×), previous / next play, and "play the drive".
- The play-by-play line and the down-and-distance under the field, so the 3D and the
  text tell the same story.
- One request loads the whole game's playback data (play records + personnel + names,
  numbers, positions, team colors); stepping between plays needs no network.

New API: `GET /api/games/{id}/playback` → plays with their events and personnel, and the
players and teams they reference.

## 7. Testing

- **Choreographer:** the §4 invariants for every play type, golden timelines for a few
  fixed plays, determinism.
- **Viewer:** Testing Library with the 3D canvas mocked: controls, scrubbing, play
  navigation, the "approximate lineup" notice.
- **End to end (Playwright):** sim a week, open a game, watch a play (canvas renders, the
  scrubber moves, the moments match the play-by-play), step to the next play.
- **Engine:** personnel is recorded for every scrimmage play, and old play logs still
  load.

## 8. Delivery plan (separate PRs, each with tests)

1. **Contract:** personnel and returners in play records (`SIM_VERSION` 1.2), typed play
   events shared by backend and frontend, the playback API.
2. **Stadium and field:** the full scene, lighting, and camera presets (replacing the
   dashboard preview's stadium).
3. **Players:** the low-poly figures, team colors and numbers, procedural poses and run
   cycle.
4. **Choreography and the viewer:** the choreographer for every play type and the Watch
   page.

## 9. Decisions (resolved)

All six were resolved with the recommended option, listed first in each item.

1. **Where choreography runs:** in the **browser, in TypeScript** (recommended): it's
   presentation, it makes scrubbing and stepping between plays instant, and it's tested
   with Vitest like the rest of the UI. Or on the **server, in Python**, next to the
   engine, served as timelines (one more round trip per play; easier to share with a
   future non-web client).
2. **Player figures:** **procedural low-poly figures** (recommended: no assets or
   licenses, fictional by construction, full control) or **rigged glTF models** with
   animation clips (more lifelike; needs a source of models and animations).
3. **Personnel:** **record it in play logs** (recommended, exact lineups) or
   **reconstruct** it from the current depth chart (no engine change, but wrong for past
   games after roster moves).
4. **Viewer placement:** a **dedicated page** `/games/[id]/watch` (recommended:
   full-screen, linkable, back button works) or a dialog over the game page.
5. **Scope:** **every play type** in Milestone 4 (recommended), or scrimmage plays
   first and kicks later.
6. **Look:** **stylized** (recommended: clean, readable, fast) or aiming for realism now.
