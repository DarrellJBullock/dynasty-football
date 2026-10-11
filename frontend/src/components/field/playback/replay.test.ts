import { describe, expect, it } from "vitest";
import type { PlaybackPlay } from "@/lib/types";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { choreograph } from "./choreograph";
import { REPLAY_SPEED, replayPlan } from "./replay";

const H = 1;
const playback = makePlayback([]);
const planFor = (play: PlaybackPlay, previous?: PlaybackPlay) => {
  const { timeline } = choreograph(play, playback);
  const at = (k: string) => timeline.moments.find((m) => m.kind === k)!.t;
  return { plan: replayPlan(play, previous, timeline), at, duration: timeline.duration };
};
const run = (yards: number) => makePlay({ result: { type: "run", yards },
  events: [{ t: "handoff", to: pid(H, "RB"), direction: "outside" },
           { t: "rush", player: pid(H, "RB"), yards }, { t: "tackle", by: [pid(2, "SS")] }] });

describe("instant replay", () => {
  it("replays a big run from the far sideline, snap to whistle, at half speed", () => {
    const { plan, at, duration } = planFor(run(34));
    expect(plan).toMatchObject({ shot: "reverse", speed: REPLAY_SPEED, reason: "big play" });
    expect(plan!.from).toBeCloseTo(at("snap") - 0.3);
    expect(plan!.to).toBeCloseTo(Math.min(duration, at("whistle") + 0.3));
  });

  it("replays passes from the skycam", () => {
    const pass = makePlay({ result: { type: "pass", yards: 28, result: "complete" },
      events: [{ t: "dropback", qb: pid(H, "QB"), depth: "deep" },
               { t: "pass", qb: pid(H, "QB"), target: pid(H, "WR"), result: "complete", air: 24, yards: 28 },
               { t: "tackle", by: [pid(2, "FS")] }] });
    expect(planFor(pass).plan?.shot).toBe("skycam");
  });

  it("leaves ordinary plays alone", () => {
    expect(planFor(run(4)).plan).toBeNull();
  });

  it("starts kicks at the kick", () => {
    const kickoff = makePlay({ down: null, distance: null, ball_on: null, personnel: null, defense: null,
      side: "away", offense: "ABQ", score: { home: 0, away: 0 }, result: { type: "kickoff" },
      events: [{ t: "kickoff", kicker: pid(2, "K"), touchback: false, return: 45, returner: pid(H, "RB") }] });
    // Not a highlight by itself; a score on it would be.
    expect(planFor(kickoff).plan).toBeNull();
    const td = { ...kickoff, score: { home: 6, away: 0 } };
    const { plan, at } = planFor(td);
    expect(plan!.from).toBeCloseTo(at("kick") - 0.3);
  });
});
