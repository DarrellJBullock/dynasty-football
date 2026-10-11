import { describe, expect, it } from "vitest";
import type { PlaybackPlay, PlayEvent } from "@/lib/types";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { cameraShot, WIDTH } from "../layout";
import { choreograph, SNAP } from "./choreograph";
import { MIN_SHOT, shotAt, shotList, type Cue } from "./director";

const H = 1;
const A = 2;
const playback = makePlayback([]);
const cuesFor = (play: PlaybackPlay) => {
  const { timeline } = choreograph(play, playback);
  return { cues: shotList(play, timeline), at: (k: string) => timeline.moments.find((m) => m.kind === k)!.t };
};

const run: PlaybackPlay = makePlay({ result: { type: "run", yards: 5 },
  events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
           { t: "rush", player: pid(H, "RB"), yards: 5 }, { t: "tackle", by: [pid(A, "MLB")] }] });
const pass = (air: number, yards: number, touchdown = false): PlaybackPlay => makePlay({
  ball_on: touchdown ? 70 : 30,
  result: { type: "pass", yards, result: "complete", touchdown },
  events: [{ t: "dropback", qb: pid(H, "QB"), depth: air >= 18 ? "deep" : "short" },
           { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR"), result: "complete", air, yards },
           ...(touchdown ? [] : [{ t: "tackle", by: [pid(A, "FS")] } as PlayEvent])] });
const kick = (events: PlayEvent[], overrides: Partial<PlaybackPlay> = {}) => makePlay({
  down: null, distance: null, ball_on: null, defense: null, personnel: null, events,
  result: { type: events[0].t }, ...overrides });

function expectSpaced(cues: Cue[]) {
  for (let i = 1; i < cues.length; i++) {
    expect(cues[i].t).toBeGreaterThan(cues[i - 1].t);
    expect(cues[i].shot).not.toBe(cues[i - 1].shot);
  }
}

describe("the director", () => {
  it("opens wide, takes the snap on the sideline, and goes tight on the tackle", () => {
    const { cues, at } = cuesFor(run);
    expect(cues[0]).toEqual({ t: 0, shot: "wide" });
    expect(cues).toContainEqual({ t: at("snap"), shot: "sideline" });
    expect(cues).toContainEqual({ t: at("tackle") - 0.3, shot: "tight" });
    expectSpaced(cues);
  });

  it("pulls back wide for a deep ball, then follows the catch", () => {
    const { cues, at } = cuesFor(pass(32, 40));
    const shots = cues.map((c) => c.shot);
    expect(shots).toEqual(["wide", "sideline", "wide", "sideline", "tight"]);
    expect(cues[2].t).toBe(at("throw"));
    expect(cuesFor(pass(6, 9)).cues.map((c) => c.shot)).toEqual(["wide", "sideline", "tight"]);
  });

  it("cuts to the touchdown at once", () => {
    const { cues, at } = cuesFor(pass(12, 30, true));
    expect(cues).toContainEqual({ t: at("touchdown"), shot: "tight" });
  });

  it("films field goals from behind the kicker", () => {
    const { cues } = cuesFor(kick([{ t: "field_goal", kicker: pid(H, "K"), distance: 40, good: true }],
                                  { down: 4, distance: 3, ball_on: 77 }));
    expect(cues[1]).toEqual({ t: SNAP - 0.2, shot: "endzone" });
    expect(shotAt(cues, SNAP + 1.5)).toBe("endzone"); // through the flight
  });

  it("tracks kickoffs and punts from the sideline", () => {
    const { cues, at } = cuesFor(kick([{ t: "kickoff", kicker: pid(A, "K"), touchback: false, return: 27,
                                          returner: pid(H, "RB") }], { side: "away", offense: "ABQ" }));
    expect(cues).toContainEqual({ t: at("kick"), shot: "sideline" });
    expect(cues.at(-1)!.shot).toBe("tight");
    expectSpaced(cues);
  });

  it("holds every shot long enough, except a touchdown", () => {
    for (const play of [run, pass(32, 40), pass(6, 9)]) {
      const { cues } = cuesFor(play);
      for (let i = 2; i < cues.length; i++) expect(cues[i].t - cues[i - 1].t).toBeGreaterThanOrEqual(MIN_SHOT);
    }
  });

  it("finds the shot at any moment", () => {
    const cues: Cue[] = [{ t: 0, shot: "wide" }, { t: 1, shot: "sideline" }, { t: 3, shot: "tight" }];
    expect(shotAt(cues, 0.5)).toBe("wide");
    expect(shotAt(cues, 1)).toBe("sideline");
    expect(shotAt(cues, 9)).toBe("tight");
    expect(shotAt([], 2)).toBe("sideline");
  });
});

describe("the director's shots", () => {
  it("frames the ball from the right places", () => {
    const ball = { x: 40, y: 12 };
    const tight = cameraShot("tight", ball.x, 1, 0, ball.y);
    const sideline = cameraShot("sideline", ball.x, 1);
    const wide = cameraShot("wide", ball.x, 1);
    expect(tight.target[2]).toBeCloseTo(12 - WIDTH / 2); // on the ball, across the field
    expect(tight.position[1]).toBeLessThan(sideline.position[1]); // low...
    expect(wide.position[1]).toBeGreaterThan(sideline.position[1]); // ...and high
    const reverse = cameraShot("reverse", ball.x, 1);
    expect(reverse.position[2]).toBeLessThan(-WIDTH / 2); // the far sideline
    const sky = cameraShot("skycam", ball.x, 1, 0, ball.y);
    expect(sky.position[0]).toBeLessThan(sky.target[0]); // behind the offense, looking downfield
    expect(cameraShot("skycam", ball.x, -1, 0, ball.y).position[0])
      .toBeGreaterThan(cameraShot("skycam", ball.x, -1, 0, ball.y).target[0]);
  });
});
