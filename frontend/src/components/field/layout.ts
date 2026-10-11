/**
 * Field geometry and camera math for the 3D scenes. Pure (no three.js), so it's unit-tested.
 *
 * Field coordinates are in yards, as in the play timeline (docs/design/play-playback.md):
 * `x` runs along the field from one back line (0) to the other (120), end zones included —
 * the goal lines are at 10 and 110; `y` runs across it from one sideline (0) to the other
 * (53.3). The scene is centered on midfield with +Y up: scene X = x − 60, scene Z = y − 26.65.
 */

export const LENGTH = 120;
export const WIDTH = 160 / 3; // 53⅓ yards
export const END_ZONE = 10;
export const BORDER = 2; // the white border and team area outside the lines
export const HASH_INSET = 70.75 / 3; // pro hashes: 70'9" in from each sideline
export const HASH_LENGTH = 2 / 3; // 2 ft
export const NUMBER_INSET = 9; // tops of the yard numbers, from the sideline
export const NUMBER_HEIGHT = 2; // 6 ft
export const GOALPOST = { crossbar: 10 / 3, width: 18.5 / 3, upright: 35 / 3 }; // yards

export type Vec3 = [number, number, number];

export function toScene(x: number, y: number, z = 0): Vec3 {
  return [x - LENGTH / 2, z, y - WIDTH / 2];
}

/** Every 5 yards from goal line to goal line (21 lines; the goal lines are the first and
 * last). */
export function yardLines(): number[] {
  return Array.from({ length: 21 }, (_, i) => END_ZONE + i * 5);
}

/** Yard numbers every 10 yards: "10" … "50" … "10", with the field x they're centered on. */
export function yardNumbers(): { x: number; label: string }[] {
  return Array.from({ length: 9 }, (_, i) => {
    const x = END_ZONE + (i + 1) * 10;
    const fromGoal = x <= 60 ? x - END_ZONE : LENGTH - END_ZONE - x;
    return { x, label: String(fromGoal) };
  });
}

/** The across-the-field positions of the hash rows (and of the short marks at each
 * sideline), each a 2-ft tick at every yard between the goal lines. */
export function hashRows(): number[] {
  return [1, HASH_INSET, WIDTH - HASH_INSET, WIDTH - 1];
}

/** Field x of a yard line given as yards from one team's goal line (`ball_on` in play
 * records), with the offense going toward x = 110 (`direction` 1) or toward 10 (−1). */
export function fieldX(ballOn: number, direction: 1 | -1 = 1): number {
  return direction === 1 ? END_ZONE + ballOn : LENGTH - END_ZONE - ballOn;
}

// ---------- cameras ----------

export type CameraPreset = "overview" | "sideline" | "endzone" | "all22";

export const CAMERA_PRESETS: { key: CameraPreset; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "sideline", label: "Sideline" },
  { key: "endzone", label: "End zone" },
  { key: "all22", label: "All-22" },
];

/** The cameras for watching plays: the broadcast director, or a fixed preset. */
export type CameraChoice = CameraPreset | "broadcast";
export const PLAY_CAMERAS: { key: CameraChoice; label: string }[] = [
  { key: "broadcast", label: "Broadcast" },
  ...CAMERA_PRESETS.filter((c) => c.key !== "overview"),
];

export interface CameraShot {
  position: Vec3; // scene coordinates
  target: Vec3;
  fov: number;
}

/**
 * Where a preset puts the camera, framing the action at field x `focus` with the offense
 * driving toward `direction`. The overview orbits midfield; `time` (seconds) turns it.
 */
/** Every shot the cameras can take: the presets, plus the broadcast director's own
 * (docs/design/broadcast.md §4). */
export type ShotName = CameraPreset | "wide" | "tight" | "skycam" | "reverse";

/**
 * Where the camera sits and looks for `shot`, framing field x `focus` (and, for the close
 * shots, field y `focusY`), with the offense driving toward `direction`.
 */
export function cameraShot(shot: ShotName, focus = LENGTH / 2, direction: 1 | -1 = 1,
                           time = 0, focusY = WIDTH / 2): CameraShot {
  const x = Math.min(Math.max(focus, END_ZONE), LENGTH - END_ZONE);
  const [sx] = toScene(x, WIDTH / 2);
  // The close shots follow the ball into the end zones and across the field.
  const [cx, , cz] = toScene(Math.min(Math.max(focus, 3), LENGTH - 3), Math.min(Math.max(focusY, 2), WIDTH - 2));
  switch (shot) {
    case "wide": // the establishing shot: higher and wider than the sideline camera
      return { position: [sx, 34, WIDTH / 2 + 52], target: [sx + direction * 4, 0, 0], fov: 34 };
    case "tight": // low and close on the ball, from the near side
      return { position: [cx - direction * 3, 7, cz + 15], target: [cx, 1, cz], fov: 30 };
    case "skycam": // behind and above the offense, looking downfield
      return { position: [cx - direction * 13, 13, cz * 0.6], target: [cx + direction * 10, 0, cz * 0.8],
               fov: 55 };
    case "reverse": // the far sideline, for replays
      return { position: [sx, 20, -(WIDTH / 2 + 36)], target: [sx - direction * 4, 0, 0], fov: 26 };
    case "sideline": // the broadcast camera: high on the near sideline, square to the line, zoomed in
      return { position: [sx, 20, WIDTH / 2 + 36], target: [sx + direction * 4, 0, 0], fov: 26 };
    case "endzone": // behind the offense, looking downfield
      return { position: [sx - direction * 34, 15, 0], target: [sx + direction * 12, 0, 0],
               fov: 45 };
    case "all22": // high and wide enough to see all 22 players
      return { position: [sx - direction * 6, 62, WIDTH / 2 + 22], target: [sx + direction * 6, 0, 0],
               fov: 40 };
    case "overview": {
      const angle = -0.5 + time * 0.08;
      return { position: [Math.sin(angle) * 92, 58, Math.cos(angle) * 92], target: [0, 0, 0],
               fov: 42 };
    }
  }
}
