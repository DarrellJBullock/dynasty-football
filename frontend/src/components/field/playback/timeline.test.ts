import { describe, expect, it } from "vitest";
import { STRIDE } from "../players/poses";
import { PlayClock } from "./clock";
import { anglesAt, ballAt, distanceAt, facingAt, positionAt, velocityAt, type PlayTimeline,
         type TimelinePlayer } from "./timeline";

const runner: TimelinePlayer = {
  id: 1, side: "offense", teamId: 1, role: "RB", name: "R. Back", number: 28, position: "RB",
  heightIn: 70, weightLb: 215, facing: 0,
  path: [{ t: 0, x: 10, y: 20 }, { t: 1, x: 10, y: 20 }, { t: 2, x: 18, y: 20 }, { t: 3, x: 18, y: 26 }],
  poses: [{ t: 0, pose: "stance2" }, { t: 1, pose: "run" }, { t: 3, pose: "down", face: Math.PI }],
};

describe("timeline sampling", () => {
  it("interpolates positions and holds the ends", () => {
    expect(positionAt(runner.path, -1)).toEqual({ x: 10, y: 20 });
    expect(positionAt(runner.path, 1.5)).toEqual({ x: 14, y: 20 });
    expect(positionAt(runner.path, 2.5)).toEqual({ x: 18, y: 23 });
    expect(positionAt(runner.path, 9)).toEqual({ x: 18, y: 26 });
  });

  it("measures distance and speed along the path", () => {
    expect(distanceAt(runner.path, 0.5)).toBe(0);
    expect(distanceAt(runner.path, 2.5)).toBeCloseTo(11);
    expect(distanceAt(runner.path, 9)).toBeCloseTo(14);
    expect(velocityAt(runner.path, 1.5)).toEqual({ speed: 8, heading: 0 });
    expect(velocityAt(runner.path, 0.5).heading).toBeNull();
  });

  it("faces the way he moves, keeps facing when he stops, or as the pose pins it", () => {
    expect(facingAt(runner, 0.5)).toBe(0); // the starting facing
    expect(facingAt(runner, 2.5)).toBeCloseTo(Math.PI / 2);
    expect(facingAt(runner, 3.5)).toBe(Math.PI);
  });

  it("blends into each new pose and runs in step with the ground covered", () => {
    expect(anglesAt(runner, 0.5).crouch).toBeCloseTo(0.16); // stance2
    const settled = anglesAt(runner, 1.2);
    const blending = anglesAt(runner, 1.05);
    expect(blending.torso).not.toBeCloseTo(settled.torso);
    // One full cycle every two strides: same legs after 2 × STRIDE yards at full speed.
    const t = 1.2 + (2 * STRIDE) / 8;
    expect(anglesAt(runner, t).hipL).toBeCloseTo(settled.hipL, 5);
    expect(anglesAt(runner, 4).lie).toBe(1);
  });

  it("puts the ball in hands, in the air on an arc, or on the ground", () => {
    const timeline = {
      ball: [
        { kind: "rest", from: 0, to: 1, at: [10, 20, 0.1] },
        { kind: "held", from: 1, to: 2, player: 1 },
        { kind: "flight", from: 2, to: 4, start: [10, 20, 2], end: [30, 20, 2], apex: 5 },
      ],
    } as PlayTimeline;
    const hands = () => [1, 2, 3] as [number, number, number];
    expect(ballAt(timeline, 0.5, hands)).toEqual([10, 20, 0.1]);
    expect(ballAt(timeline, 1.5, hands)).toEqual([1, 2, 3]);
    expect(ballAt(timeline, 3, hands)).toEqual([20, 20, 7]); // halfway: the apex
    expect(ballAt(timeline, 9, hands)).toEqual([30, 20, 2]);
  });
});

describe("PlayClock", () => {
  it("advances at its speed while playing and stops at the end", () => {
    const clock = new PlayClock();
    expect(clock.advance(0.05, 1)).toBe(false);
    expect(clock.time).toBeCloseTo(0.05);
    clock.setSpeed(2);
    clock.advance(0.05, 1);
    expect(clock.time).toBeCloseTo(0.15);
    clock.advance(5, 1); // a long frame (a background tab) counts as at most 0.1 s
    expect(clock.time).toBeCloseTo(0.35);
    clock.seek(0.95);
    expect(clock.advance(0.1, 1)).toBe(true);
    expect(clock.time).toBe(1);
    expect(clock.playing).toBe(false);
    expect(clock.advance(0.1, 1)).toBe(false);
  });
});
