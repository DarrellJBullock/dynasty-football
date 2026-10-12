import { describe, expect, it } from "vitest";
import { CameraFollower } from "./cameraFollow";
import { cameraShot } from "./layout";

const aim = { preset: "sideline" as const, focus: 60, direction: 1 as const, time: 0 };

describe("the camera's motion", () => {
  it("starts on the shot, then eases toward a new one", () => {
    const camera = new CameraFollower();
    expect(camera.step(aim, 1 / 60, false)).toEqual(cameraShot("sideline", 60, 1));
    const goal = cameraShot("sideline", 80, 1);
    const next = camera.step({ ...aim, focus: 80 }, 1 / 60, false);
    expect(next.position[0]).toBeGreaterThan(cameraShot("sideline", 60, 1).position[0]);
    expect(next.position[0]).toBeLessThan(goal.position[0]); // on its way, not there
    for (let i = 0; i < 300; i++) camera.step({ ...aim, focus: 80 }, 1 / 60, false);
    expect(camera.position![0]).toBeCloseTo(goal.position[0], 3);
  });

  it("follows the ball when asked", () => {
    const camera = new CameraFollower();
    expect(camera.step({ ...aim, follow: 90 }, 1 / 60, false)).toEqual(cameraShot("sideline", 90, 1));
  });

  it("cuts when the director changes shot, and eases within one", () => {
    const camera = new CameraFollower();
    camera.step({ ...aim, directed: { shot: "wide", x: 60, y: 26 } }, 1 / 60, false);
    const cut = camera.step({ ...aim, directed: { shot: "tight", x: 62, y: 20 } }, 1 / 60, false);
    expect(cut).toEqual(cameraShot("tight", 62, 1, 0, 20));
    const eased = camera.step({ ...aim, directed: { shot: "tight", x: 70, y: 20 } }, 1 / 60, false);
    expect(eased.position).not.toEqual(cameraShot("tight", 70, 1, 0, 20).position);
  });

  it("always cuts for visitors who want less motion", () => {
    const camera = new CameraFollower();
    camera.step(aim, 1 / 60, true);
    expect(camera.step({ ...aim, focus: 80 }, 1 / 60, true)).toEqual(cameraShot("sideline", 80, 1));
  });
});
