/**
 * Pre-snap alignments, in the order play logs record each side's personnel
 * (backend app/sim/resolve.py: offense QB, RB, WR×3, TE, OT×2, OG×2, C; defense DE×2, DT×2,
 * OLB×n, MLB, CB×n, FS, SS). Pure.
 *
 * A spot is `depth` yards off the line of scrimmage (into its own backfield) and `lateral`
 * yards from the ball, positive toward the offense's right.
 */

export interface Spot {
  role: string;
  position: string;
  depth: number;
  lateral: number;
  stance: "stance3" | "stance2";
}

/** Typical size by position (inches, pounds) and a typical number by role, for players
 * who aren't on a real roster (the dashboard's stadium, stand-ins in replays). */
export const TYPICAL: Record<string, [number, number]> = {
  QB: [75, 225], RB: [70, 215], WR: [73, 200], TE: [77, 250], OT: [78, 315], OG: [76, 315],
  C: [75, 305], DE: [76, 270], DT: [75, 310], OLB: [75, 245], MLB: [74, 240], CB: [71, 195],
  FS: [72, 205], SS: [72, 210], K: [72, 195], P: [74, 210],
};
export const NUMBERS: Record<string, number> = {
  QB: 12, RB: 28, X: 11, Z: 84, SLOT: 17, TE: 87, LT: 74, RT: 71, LG: 66, RG: 63, C: 55,
  LDE: 91, RDE: 97, LDT: 93, RDT: 99, SAM: 52, WILL: 54, MIKE: 50, CB1: 24, CB2: 21, NB: 31,
  DB: 37, FS: 29, SS: 33,
};

export type Package = "base" | "nickel" | "dime";

export function offenseSpots(): Spot[] {
  return [
    { role: "QB", position: "QB", depth: 1.2, lateral: 0, stance: "stance2" },
    { role: "RB", position: "RB", depth: 6.5, lateral: 0, stance: "stance2" },
    { role: "X", position: "WR", depth: 1, lateral: -17, stance: "stance2" },
    { role: "Z", position: "WR", depth: 1, lateral: 16, stance: "stance2" },
    { role: "SLOT", position: "WR", depth: 1.2, lateral: -9, stance: "stance2" },
    { role: "TE", position: "TE", depth: 1, lateral: 4.6, stance: "stance3" },
    { role: "LT", position: "OT", depth: 1, lateral: -3.6, stance: "stance3" },
    { role: "RT", position: "OT", depth: 1, lateral: 3.6, stance: "stance3" },
    { role: "LG", position: "OG", depth: 0.9, lateral: -1.8, stance: "stance3" },
    { role: "RG", position: "OG", depth: 0.9, lateral: 1.8, stance: "stance3" },
    { role: "C", position: "C", depth: 0.7, lateral: 0, stance: "stance3" },
  ];
}

/** `lateral` is from the offense's point of view, so the defense mirrors its left and right. */
export function defenseSpots(pkg: Package = "base"): Spot[] {
  const front: Spot[] = [
    { role: "LDE", position: "DE", depth: 1, lateral: 4.4, stance: "stance3" },
    { role: "RDE", position: "DE", depth: 1, lateral: -4.4, stance: "stance3" },
    { role: "LDT", position: "DT", depth: 1, lateral: 1.4, stance: "stance3" },
    { role: "RDT", position: "DT", depth: 1, lateral: -1.4, stance: "stance3" },
  ];
  const olbsByPackage: Record<Package, Spot[]> = {
    base: [
      { role: "SAM", position: "OLB", depth: 4.5, lateral: 5.5, stance: "stance2" },
      { role: "WILL", position: "OLB", depth: 4.5, lateral: -5.5, stance: "stance2" },
    ],
    nickel: [{ role: "WILL", position: "OLB", depth: 4.5, lateral: -4.5, stance: "stance2" }],
    dime: [],
  };
  const olbs = olbsByPackage[pkg];
  const corners: Spot[] = [
    { role: "CB1", position: "CB", depth: 6, lateral: -16, stance: "stance2" },
    { role: "CB2", position: "CB", depth: 6, lateral: 17, stance: "stance2" },
    ...(pkg === "base" ? [] : [{ role: "NB", position: "CB", depth: 5.5, lateral: -9,
                                 stance: "stance2" as const }]),
    ...(pkg === "dime" ? [{ role: "DB", position: "CB", depth: 6, lateral: 9,
                            stance: "stance2" as const }] : []),
  ];
  return [
    ...front, ...olbs,
    { role: "MIKE", position: "MLB", depth: 5, lateral: 0, stance: "stance2" },
    ...corners,
    { role: "FS", position: "FS", depth: 13, lateral: -3, stance: "stance2" },
    { role: "SS", position: "SS", depth: 11, lateral: 6, stance: "stance2" },
  ];
}

/**
 * Field coordinates of a spot: line of scrimmage at field x `los`, ball at field y `ballY`,
 * the offense driving toward `direction` (+1: increasing x). Defenders line up across
 * the ball, facing the other way.
 */
export function spotOnField(spot: Spot, side: "offense" | "defense", los: number, ballY: number,
                            direction: 1 | -1): { x: number; y: number; facing: number } {
  const toward = side === "offense" ? direction : -direction;
  // Facing +x with +y up the screen's depth, a player's right is +y (field y is scene +z):
  // the offense's right is +y when it drives toward +x, −y otherwise.
  return {
    x: los - toward * spot.depth,
    y: ballY + direction * spot.lateral,
    facing: toward === 1 ? 0 : Math.PI,
  };
}
