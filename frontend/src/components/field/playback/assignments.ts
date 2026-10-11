/**
 * What every player does on each named play (docs/design/coach-mode.md §5): formations,
 * routes, run schemes, coverage shells and blitzers, keyed by the play keys in the
 * backend's `app/sim/playbook.py` (a play log's `call.play` and `defense.play`). Pure data
 * plus route geometry; the choreographer draws it. Plays without a key (games before
 * SIM_VERSION 1.3) fall back to the choreographer's generic motions.
 */

export type Formation = "singleback" | "iform" | "shotgun" | "pistol";
export type Receiver = "X" | "Z" | "SLOT" | "TE" | "RB";
export type RouteName =
  | "go" | "seam" | "post" | "corner" | "out" | "in" | "dig" | "slant" | "hitch" | "curl"
  | "flat" | "wheel" | "drag" | "cross" | "sit" | "bubble" | "swing" | "block";
export type RunScheme = "zone" | "outside_zone" | "power" | "counter" | "draw" | "toss";

export interface OffensePlan {
  formation: Formation;
  scheme?: RunScheme; // runs
  routes?: Partial<Record<Receiver, RouteName>>; // passes: everyone not listed blocks
  playAction?: "fake" | "boot"; // boot: the QB rolls out away from the fake
  screen?: boolean; // the line lets the rush through, then releases to block downfield
}

/** Mirrors `OFFENSE` in backend/app/sim/playbook.py (formations), plus the routes. */
export const OFFENSE_PLANS: Record<string, OffensePlan> = {
  inside_zone: { formation: "singleback", scheme: "zone" },
  power: { formation: "iform", scheme: "power" },
  counter: { formation: "singleback", scheme: "counter" },
  draw: { formation: "shotgun", scheme: "draw" },
  outside_zone: { formation: "pistol", scheme: "outside_zone" },
  toss: { formation: "iform", scheme: "toss" },
  slants: { formation: "shotgun", routes: { X: "slant", Z: "slant", SLOT: "slant", TE: "sit" } },
  stick: { formation: "shotgun", routes: { X: "go", Z: "hitch", SLOT: "flat", TE: "sit", RB: "swing" } },
  hitches: { formation: "shotgun", routes: { X: "hitch", Z: "hitch", SLOT: "hitch", TE: "sit" } },
  curl_flat: { formation: "singleback", routes: { X: "curl", Z: "curl", SLOT: "flat", TE: "seam", RB: "swing" } },
  mesh: { formation: "shotgun", routes: { X: "go", Z: "corner", SLOT: "drag", TE: "drag", RB: "swing" } },
  smash: { formation: "shotgun", routes: { X: "hitch", Z: "hitch", SLOT: "corner", TE: "seam" } },
  flood: { formation: "singleback", routes: { X: "go", Z: "post", SLOT: "out", TE: "flat" } },
  dig: { formation: "shotgun", routes: { X: "dig", Z: "dig", SLOT: "seam", TE: "sit" } },
  y_cross: { formation: "shotgun", routes: { X: "go", Z: "post", SLOT: "drag", TE: "cross", RB: "flat" } },
  four_verts: { formation: "shotgun", routes: { X: "go", Z: "go", SLOT: "seam", TE: "seam" } },
  post_wheel: { formation: "shotgun", routes: { X: "post", Z: "curl", SLOT: "wheel", TE: "sit" } },
  pa_boot: { formation: "singleback", playAction: "boot",
             routes: { X: "go", Z: "drag", SLOT: "corner", TE: "flat" } },
  pa_crossers: { formation: "iform", playAction: "fake", routes: { X: "cross", Z: "dig", SLOT: "in", TE: "drag" } },
  pa_post: { formation: "iform", playAction: "fake", routes: { X: "post", Z: "go", SLOT: "seam" } },
  rb_screen: { formation: "shotgun", screen: true, routes: { X: "go", Z: "go", SLOT: "hitch", RB: "swing" } },
  bubble: { formation: "shotgun", routes: { SLOT: "bubble" } },
  kneel: { formation: "singleback" },
};

/**
 * A route's waypoints relative to the receiver's alignment: `[downfield, inside]` yards,
 * where positive `inside` is toward the middle of the field (the ball). The last point is
 * where the ball is caught when he's the target; the choreographer stretches the route
 * downfield to the recorded air yards.
 */
export const ROUTES: Record<RouteName, [number, number][]> = {
  go: [[3, 0], [24, 0.5]],
  seam: [[3, 0], [22, 1]],
  post: [[11, 0], [24, 7]],
  corner: [[10, 0], [20, -7]],
  out: [[10, 0], [10, -6]],
  in: [[10, 0], [10, 7]],
  dig: [[14, 0], [14, 10]],
  slant: [[1.5, 0], [7, 5]],
  hitch: [[5.5, 0], [5, 0]],
  curl: [[12, 0], [10.5, 1.5]],
  flat: [[1, -1], [3, -7]],
  wheel: [[1, -3], [6, -7], [22, -7]],
  drag: [[1.5, 0.5], [5, 14]],
  cross: [[6, 0], [13, 17]],
  sit: [[6, 0], [6, 0.5]],
  bubble: [[-1.2, -2], [-1, -5]],
  swing: [[-1, -2.5], [0.5, -7]],
  block: [],
};

export type DefenseRole = "LDE" | "RDE" | "LDT" | "RDT" | "SAM" | "WILL" | "MIKE" | "CB1" | "CB2"
  | "NB" | "DB" | "FS" | "SS";

/** A defender's job: drop to a zone `[downfield, toward the offense's right]` from the
 * ball, cover a receiver man to man, or rush the quarterback. */
export type DefenseJob = { zone: [number, number] } | { man: Receiver } | { rush: true };

export interface DefensePlan {
  /** Who rushes besides the four linemen, in order of preference (the first who's on the
   * field in this package goes). */
  blitz?: DefenseRole[];
  jobs: Partial<Record<DefenseRole, DefenseJob>>;
}

const zone = (u: number, v: number): DefenseJob => ({ zone: [u, v] });
const man = (r: Receiver): DefenseJob => ({ man: r });
const RUSH: DefenseJob = { rush: true };

// Underneath zones shared by the two-deep shells.
const UNDER_TWO = { SAM: zone(8, 8), WILL: zone(8, -8), MIKE: zone(9, 0), NB: zone(7, -12), DB: zone(7, 12) };

/** Mirrors `DEFENSE` in backend/app/sim/playbook.py. */
export const DEFENSE_PLANS: Record<string, DefensePlan> = {
  cover2: { jobs: { ...UNDER_TWO, CB1: zone(5, -18), CB2: zone(5, 18), FS: zone(18, -10), SS: zone(18, 10) } },
  tampa2: { jobs: { ...UNDER_TWO, MIKE: zone(16, 0), CB1: zone(5, -18), CB2: zone(5, 18),
                    FS: zone(19, -11), SS: zone(19, 11) } },
  cover3: { jobs: { CB1: zone(16, -17), CB2: zone(16, 17), FS: zone(19, 0), SS: zone(7, 12),
                    SAM: zone(7, 6), WILL: zone(8, -6), MIKE: zone(8, 1), NB: zone(6, -13), DB: zone(6, 13) } },
  cover4: { jobs: { CB1: zone(15, -17), CB2: zone(15, 17), FS: zone(14, -6), SS: zone(14, 6),
                    SAM: zone(6, 10), WILL: zone(6, -10), MIKE: zone(8, 0), NB: zone(6, -13), DB: zone(6, 13) } },
  cover1: { jobs: { CB1: man("X"), CB2: man("Z"), NB: man("SLOT"), SS: man("TE"), WILL: man("RB"),
                    FS: zone(18, 0), MIKE: zone(6, 0), SAM: zone(7, 6), DB: zone(8, 8) } },
  two_man: { jobs: { CB1: man("X"), CB2: man("Z"), NB: man("SLOT"), SAM: man("TE"), DB: man("TE"),
                     WILL: man("RB"), MIKE: zone(6, 0), FS: zone(19, -10), SS: zone(19, 10) } },
  cover0: { blitz: ["MIKE", "SAM", "DB"],
            jobs: { CB1: man("X"), CB2: man("Z"), NB: man("SLOT"), SS: man("TE"), WILL: man("RB"),
                    FS: man("RB"), SAM: man("TE") } },
  mike_blitz: { blitz: ["MIKE"],
                jobs: { CB1: man("X"), CB2: man("Z"), NB: man("SLOT"), SS: man("TE"), WILL: man("RB"),
                        FS: zone(18, 0), SAM: zone(7, 6), DB: zone(8, 8) } },
  fire_zone: { blitz: ["WILL", "NB", "SAM"],
               jobs: { LDE: zone(6, 6), CB1: zone(16, -17), CB2: zone(16, 17), FS: zone(19, 0),
                       SS: zone(7, 11), MIKE: zone(8, 0), SAM: zone(7, -8), NB: zone(6, -12), DB: zone(6, 12) } },
  edge_blitz: { blitz: ["SAM", "WILL", "NB"],
                jobs: { ...UNDER_TWO, CB1: zone(5, -18), CB2: zone(5, 18), FS: zone(18, -10), SS: zone(18, 10) } },
  prevent: { jobs: { CB1: zone(20, -16), CB2: zone(20, 16), FS: zone(28, -8), SS: zone(28, 8),
                     NB: zone(14, -11), DB: zone(14, 11), MIKE: zone(12, 0), WILL: zone(10, -6), SAM: zone(10, 6) } },
};

/** The defenders who rush on this call, given who's on the field. */
export function blitzers(plan: DefensePlan | undefined, onField: Set<string>): DefenseRole[] {
  if (!plan?.blitz) return [];
  const first = plan.blitz.find((role) => onField.has(role));
  return first ? [first] : [];
}

/** A defender's job on this call; rushers rush, and the defensive line rushes unless the
 * call drops one into coverage. */
export function jobOf(plan: DefensePlan | undefined, role: string, rushing: DefenseRole[]): DefenseJob | null {
  if (rushing.includes(role as DefenseRole)) return RUSH;
  const job = plan?.jobs[role as DefenseRole];
  if (job) return job;
  return ["LDE", "RDE", "LDT", "RDT"].includes(role) ? RUSH : null;
}
