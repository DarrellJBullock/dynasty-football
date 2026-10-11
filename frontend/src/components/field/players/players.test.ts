import { describe, expect, it } from "vitest";
import { defenseSpots, offenseSpots, spotOnField } from "./formations";
import { AWAY_JERSEY, contrast, kit, skinTone } from "./kit";
import { blend, build, hipHeight, pose, POSES, runPhase, STRIDE } from "./poses";

describe("poses", () => {
  it("defines every pose with finite joint angles", () => {
    for (const name of POSES) {
      const angles = pose(name, 1.3, 0.5);
      expect(Object.values(angles).every(Number.isFinite)).toBe(true);
    }
  });

  it("runs a full cycle every two strides, legs opposed", () => {
    expect(runPhase(2 * STRIDE)).toBeCloseTo(Math.PI * 2);
    const mid = pose("run", Math.PI / 2);
    expect(mid.hipL).toBeCloseTo(-mid.hipR);
    expect(mid.hipL).toBeGreaterThan(0.5);
    expect(pose("run", 0).hipL).toBeCloseTo(pose("run", runPhase(2 * STRIDE)).hipL);
    // Arms swing against the legs.
    expect(Math.sign(mid.shoulderR - mid.torso)).toBe(Math.sign(mid.hipL));
  });

  it("tucks the ball when carrying and winds up before releasing a throw", () => {
    expect(pose("carry", 1).elbowR).toBeGreaterThan(pose("run", 1).elbowR);
    expect(pose("throw", 0, 0.5).shoulderR).toBeLessThan(0); // arm cocked back
    expect(pose("throw", 0, 1).shoulderR).toBeGreaterThan(1); // through the release
  });

  it("leaning players reach forward: arms past the torso's lean", () => {
    for (const name of ["stance3", "block", "dive"] as const) {
      const a = pose(name);
      expect(a.shoulderR - a.torso).toBeGreaterThan(0);
    }
  });

  it("blends between poses", () => {
    const a = pose("stand");
    const b = pose("stance3");
    expect(blend(a, b, 0)).toEqual(a);
    expect(blend(a, b, 1)).toEqual(b);
    expect(blend(a, b, 0.5).torso).toBeCloseTo((a.torso + b.torso) / 2);
    expect(blend(a, b, 2)).toEqual(b); // clamped
  });
});

describe("builds", () => {
  it("makes linemen bulkier than receivers", () => {
    const lineman = build(78, 315);
    const receiver = build(73, 195);
    expect(lineman.bulk).toBeGreaterThan(receiver.bulk + 0.2);
    expect(lineman.height).toBeCloseTo(78 / 36);
  });

  it("keeps the hips at standing height upright and low in a stance or on the ground", () => {
    const b = build(74, 230);
    const standing = hipHeight(b, pose("stand"));
    expect(standing).toBeCloseTo(b.thigh + b.shin, 1);
    expect(hipHeight(b, pose("stance3"))).toBeLessThan(standing * 0.75);
    expect(hipHeight(b, pose("down"))).toBeLessThan(standing * 0.4);
  });
});

describe("formations", () => {
  it("lines up 11 on each side in the play log's personnel order", () => {
    expect(offenseSpots().map((s) => s.position)).toEqual(
      ["QB", "RB", "WR", "WR", "WR", "TE", "OT", "OT", "OG", "OG", "C"]);
    for (const pkg of ["base", "nickel", "dime"] as const) {
      const spots = defenseSpots(pkg);
      expect(spots).toHaveLength(11);
      expect(spots.filter((s) => s.position === "CB")).toHaveLength({ base: 2, nickel: 3, dime: 4 }[pkg]);
      expect(spots.filter((s) => s.position === "OLB")).toHaveLength({ base: 2, nickel: 1, dime: 0 }[pkg]);
    }
  });

  it("places each side on its own side of the ball, facing the other", () => {
    for (const direction of [1, -1] as const) {
      const offense = offenseSpots().map((s) => spotOnField(s, "offense", 40, 26, direction));
      const defense = defenseSpots("nickel").map((s) => spotOnField(s, "defense", 40, 26, direction));
      expect(offense.every((p) => (p.x - 40) * direction < 0)).toBe(true);
      expect(defense.every((p) => (p.x - 40) * direction > 0)).toBe(true);
      expect(new Set(offense.map((p) => p.facing)).size).toBe(1);
      expect(offense[0].facing).not.toBe(defense[0].facing);
      const all = [...offense, ...defense].map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`);
      expect(new Set(all).size).toBe(22);
    }
  });

  it("puts the right tackle on the offense's right in either direction", () => {
    const rt = offenseSpots().find((s) => s.role === "RT")!;
    // Driving toward +x, the offense's right is +y; driving toward −x, it's −y.
    expect(spotOnField(rt, "offense", 50, 26, 1).y).toBeGreaterThan(26);
    expect(spotOnField(rt, "offense", 50, 26, -1).y).toBeLessThan(26);
  });
});

describe("kits", () => {
  const team = { primary_color: "#0b2545", secondary_color: "#c9a227" };
  it("puts the home team in its color and the away team in white", () => {
    expect(kit(team, true).jersey).toBe(team.primary_color);
    expect(kit(team, false).jersey).toBe(AWAY_JERSEY);
  });

  it("chooses readable numbers", () => {
    for (const home of [true, false]) {
      const k = kit(team, home);
      expect(contrast(k.jersey, k.numbers)).toBeGreaterThan(3);
    }
    // Low-contrast team colors fall back to white or black numbers.
    const muddy = kit({ primary_color: "#555555", secondary_color: "#666666" }, true);
    expect(contrast(muddy.jersey, muddy.numbers)).toBeGreaterThan(3);
  });

  it("gives each player a stable skin tone", () => {
    expect(skinTone(42)).toBe(skinTone(42));
    expect(new Set(Array.from({ length: 40 }, (_, i) => skinTone(i))).size).toBeGreaterThan(3);
  });
});
