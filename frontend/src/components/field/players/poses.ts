/**
 * Procedural poses for the low-poly players. Pure: a pose is a set of joint angles
 * (radians) the figure applies to its skeleton.
 *
 * Conventions (the figure faces +x, up is +y, its right side is +z):
 * - hip / shoulder: forward swing of the leg / arm (positive = forward)
 * - knee: bend (positive = the shin folds back)
 * - elbow: bend (positive = the forearm folds forward)
 * - spread: arm raised out to the side
 * - torso: forward lean. Arms hang from the torso, so an arm's angle to the vertical is
 *   its shoulder angle minus the lean: a leaning player reaches forward with shoulder ≈ lean.
 * - crouch: how far the hips drop, as a share of leg length
 * - lie: 0 standing … 1 lying face down
 */

export interface JointAngles {
  hipL: number; hipR: number;
  kneeL: number; kneeR: number;
  shoulderL: number; shoulderR: number;
  elbowL: number; elbowR: number;
  spreadL: number; spreadR: number;
  torso: number;
  crouch: number;
  lie: number;
}

export type Pose =
  | "stand" | "stance3" | "stance2" | "run" | "carry" | "block" | "throw" | "catch"
  | "dive" | "down" | "celebrate";

export const POSES: Pose[] = ["stand", "stance3", "stance2", "run", "carry", "block", "throw",
  "catch", "dive", "down", "celebrate"];

const ZERO: JointAngles = {
  hipL: 0, hipR: 0, kneeL: 0, kneeR: 0, shoulderL: 0, shoulderR: 0, elbowL: 0, elbowR: 0,
  spreadL: 0.08, spreadR: 0.08, torso: 0, crouch: 0, lie: 0,
};

/** Stride length in yards at full speed (a run cycle covers two strides). */
export const STRIDE = 2.1;

/** Phase (radians) of the run cycle after covering `distance` yards. Driving the cycle by
 * distance keeps feet and ground in step, and makes scrubbing exact. */
export function runPhase(distance: number): number {
  return (distance / (2 * STRIDE)) * Math.PI * 2;
}

/**
 * The joint angles of `pose`.
 * - `phase`: run-cycle phase for run and carry (see runPhase)
 * - `progress`: 0–1 through a one-off motion (the throw's windup and release)
 * - `effort`: 0–1, how hard he's running (lean and arm drive grow with it)
 */
export function pose(name: Pose, phase = 0, progress = 0, effort = 1): JointAngles {
  switch (name) {
    case "stand":
      return { ...ZERO, elbowL: 0.2, elbowR: 0.2 };
    case "stance3": // lineman: hips low, weight forward, one hand down
      return { ...ZERO, hipL: 1.35, hipR: 1.15, kneeL: 1.7, kneeR: 1.4, torso: 1.15, crouch: 0.42,
               shoulderR: 1.35, elbowR: 0.05, shoulderL: 0.95, elbowL: 1.3 };
    case "stance2": // skill player: upright crouch, hands on knees
      return { ...ZERO, hipL: 0.55, hipR: 0.45, kneeL: 0.8, kneeR: 0.7, torso: 0.45, crouch: 0.16,
               shoulderL: 0.75, shoulderR: 0.75, elbowL: 0.2, elbowR: 0.2 };
    case "run":
    case "carry": {
      const s = Math.sin(phase);
      const legs = 0.75 * effort + 0.15;
      const angles: JointAngles = {
        ...ZERO,
        hipL: legs * s, hipR: -legs * s,
        kneeL: 0.25 + 1.1 * Math.max(0, -Math.sin(phase - 0.6)) * effort,
        kneeR: 0.25 + 1.1 * Math.max(0, Math.sin(phase - 0.6)) * effort,
        torso: 0.12 + 0.2 * effort,
        elbowL: 1.4, elbowR: 1.4,
        crouch: 0.05 + 0.04 * Math.abs(Math.cos(phase)),
      };
      angles.shoulderL = angles.torso - 0.8 * effort * s; // arms swing opposite the legs
      angles.shoulderR = angles.torso + 0.8 * effort * s;
      if (name === "carry") { // ball tucked under the right arm
        angles.shoulderR = angles.torso + 0.35;
        angles.elbowR = 1.9;
      }
      return angles;
    }
    case "block": // engaged: low, arms extended into the man in front
      return { ...ZERO, hipL: 0.9, hipR: 0.3, kneeL: 1.0, kneeR: 0.6, torso: 0.6, crouch: 0.2,
               shoulderL: 1.9, shoulderR: 1.9, elbowL: 0.35, elbowR: 0.35 };
    case "throw": { // windup (arm back) to release (arm through)
      const p = Math.min(Math.max(progress, 0), 1);
      const release = p < 0.6 ? -2.4 * (p / 0.6) : -2.4 + 3.8 * ((p - 0.6) / 0.4);
      return { ...ZERO, hipL: 0.35, hipR: -0.25, kneeL: 0.3, kneeR: 0.2, torso: 0.1 + 0.25 * p,
               crouch: 0.06, shoulderR: release, elbowR: p < 0.6 ? 1.6 : 1.6 - 1.4 * ((p - 0.6) / 0.4),
               shoulderL: 0.9 - 0.6 * p, elbowL: 0.8, spreadR: 0.4 };
    }
    case "catch": // arms up and out in front, reaching
      return { ...ZERO, hipL: 0.2, kneeL: 0.2, kneeR: 0.15, torso: -0.05,
               shoulderL: 2.5, shoulderR: 2.5, elbowL: 0.25, elbowR: 0.25, spreadL: 0.2, spreadR: 0.2 };
    case "dive": // tackling: horizontal, arms wrapping forward, legs driving behind
      return { ...ZERO, hipL: -0.35, hipR: -0.5, kneeL: 0.4, kneeR: 0.6, torso: 1.35, crouch: 0.5,
               shoulderL: 2.9, shoulderR: 2.9, elbowL: 0.5, elbowR: 0.5, lie: 0.35 };
    case "down":
      return { ...ZERO, hipL: 0.1, kneeL: 0.3, kneeR: 0.1, shoulderL: 0.4, shoulderR: 2.6,
               elbowL: 0.6, elbowR: 0.4, lie: 1 };
    case "celebrate": // both arms up
      return { ...ZERO, shoulderL: 2.9, shoulderR: 2.9, elbowL: 0.15, elbowR: 0.15, spreadL: 0.35,
               spreadR: 0.35 };
  }
}

/** Linear blend between two poses: `t` 0 → a, 1 → b. */
export function blend(a: JointAngles, b: JointAngles, t: number): JointAngles {
  const k = Math.min(Math.max(t, 0), 1);
  const out = { ...a };
  for (const key of Object.keys(a) as (keyof JointAngles)[]) out[key] = a[key] * (1 - k) + b[key] * k;
  return out;
}

/** Figure proportions in yards, from a player's height (inches) and weight (pounds). */
export interface Build {
  height: number; // yards
  bulk: number; // width scale: ~0.9 for a receiver, ~1.3 for a lineman
  thigh: number; shin: number; torso: number; head: number; upperArm: number; forearm: number;
}

export function build(heightIn: number, weightLb: number): Build {
  const height = heightIn / 36;
  const bmi = (weightLb / (heightIn * heightIn)) * 703; // ~25 receivers, ~40 linemen
  const bulk = Math.min(1.45, Math.max(0.85, 0.5 + bmi / 50));
  return { height, bulk, thigh: height * 0.245, shin: height * 0.235, torso: height * 0.3,
           head: height * 0.13, upperArm: height * 0.17, forearm: height * 0.16 };
}

/** How high the hips sit for a pose, so the planted foot stays on the ground. */
export function hipHeight(b: Build, angles: JointAngles): number {
  const leg = (hip: number, knee: number) => b.thigh * Math.cos(hip) + b.shin * Math.cos(hip - knee);
  const standing = Math.max(leg(angles.hipL, angles.kneeL), leg(angles.hipR, angles.kneeR));
  return Math.max(0.15, standing * (1 - angles.lie * 0.75));
}
