import { describe, expect, it } from "vitest";
import {
  CAMERA_PRESETS,
  HASH_INSET,
  LENGTH,
  WIDTH,
  cameraShot,
  fieldX,
  hashRows,
  toScene,
  yardLines,
  yardNumbers,
} from "./layout";

describe("field layout", () => {
  it("centers the scene on midfield", () => {
    expect(toScene(60, WIDTH / 2)).toEqual([0, 0, 0]);
    expect(toScene(0, 0, 3)).toEqual([-60, 3, -WIDTH / 2]);
  });

  it("has yard lines every 5 yards goal line to goal line", () => {
    const lines = yardLines();
    expect(lines).toHaveLength(21);
    expect(lines[0]).toBe(10);
    expect(lines.at(-1)).toBe(110);
  });

  it("numbers count up to the 50 and back down", () => {
    expect(yardNumbers().map((n) => n.label)).toEqual(
      ["10", "20", "30", "40", "50", "40", "30", "20", "10"]);
    expect(yardNumbers()[4].x).toBe(60);
  });

  it("puts the hashes at pro width, symmetrically", () => {
    const [, near, far] = hashRows();
    expect(near).toBeCloseTo(HASH_INSET);
    expect(near + far).toBeCloseTo(WIDTH);
    expect(far - near).toBeCloseTo(18.5 / 3); // 18'6", the width of the goal posts
  });

  it("converts yard lines for either direction", () => {
    expect(fieldX(25, 1)).toBe(35);
    expect(fieldX(25, -1)).toBe(85);
    expect(fieldX(50, 1)).toBe(fieldX(50, -1));
  });
});

describe("camera presets", () => {
  it("covers every preset", () => {
    expect(CAMERA_PRESETS.map((p) => p.key)).toEqual(["overview", "sideline", "endzone", "all22"]);
  });

  it("frames the line of scrimmage from the right places", () => {
    const [losX] = toScene(35, WIDTH / 2);
    const sideline = cameraShot("sideline", 35, 1);
    expect(sideline.position[2]).toBeGreaterThan(WIDTH / 2); // off the near sideline
    expect(Math.abs(sideline.target[0] - losX)).toBeLessThan(8);

    const endzone = cameraShot("endzone", 35, 1);
    expect(endzone.position[0]).toBeLessThan(losX); // behind the offense...
    expect(cameraShot("endzone", 35, -1).position[0]).toBeGreaterThan(losX); // ...either way
    expect(cameraShot("all22", 35, 1).position[1]).toBeGreaterThan(sideline.position[1]);
  });

  it("keeps the focus between the goal lines and orbits the overview", () => {
    expect(cameraShot("sideline", -20).target[0]).toBe(cameraShot("sideline", 10).target[0]);
    expect(cameraShot("sideline", LENGTH + 20).target[0]).toBe(cameraShot("sideline", 110).target[0]);
    const a = cameraShot("overview", 60, 1, 0).position;
    const b = cameraShot("overview", 60, 1, 10).position;
    expect(a).not.toEqual(b);
    expect(Math.hypot(a[0], a[2])).toBeCloseTo(Math.hypot(b[0], b[2]));
  });
});
