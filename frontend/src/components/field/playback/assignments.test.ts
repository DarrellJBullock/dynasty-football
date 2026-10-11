import { describe, expect, it } from "vitest";
import type { PlaybackPlay, PlayEvent } from "@/lib/types";
import { makePlay, makePlayback, pid, team } from "@/test/fixtures";
import { fieldX, LENGTH, WIDTH } from "../layout";
import { DEFENSE_PLANS, OFFENSE_PLANS, ROUTES } from "./assignments";
import { choreograph, SNAP } from "./choreograph";
import { ballAt, handsAt, positionAt, type PlayTimeline, type TimelinePlayer } from "./timeline";

const H = team.id;
const A = 2;
const playback = makePlayback([]);

// The backend's named plays (app/sim/playbook.py), minus the kicks.
const OFFENSE_KEYS = ["inside_zone", "power", "counter", "draw", "outside_zone", "toss", "slants",
  "stick", "hitches", "curl_flat", "mesh", "smash", "flood", "dig", "y_cross", "four_verts",
  "post_wheel", "pa_boot", "pa_crossers", "pa_post", "rb_screen", "bubble", "kneel"];
const DEFENSE_KEYS = ["cover2", "tampa2", "cover3", "cover4", "cover1", "two_man", "cover0",
  "mike_blitz", "fire_zone", "edge_blitz", "prevent"];
const DEPTH: Record<string, "screen" | "short" | "medium" | "deep"> = {
  slants: "short", stick: "short", hitches: "short", curl_flat: "short", mesh: "short",
  smash: "medium", flood: "medium", dig: "medium", y_cross: "medium", four_verts: "deep",
  post_wheel: "deep", pa_boot: "short", pa_crossers: "medium", pa_post: "deep", rb_screen: "screen",
  bubble: "screen",
};
const AIR = { screen: -1, short: 6, medium: 13, deep: 30 };
const COVERAGE: Record<string, [string, boolean]> = {
  cover2: ["zone", false], tampa2: ["zone", false], cover3: ["zone", false], cover4: ["zone", false],
  cover1: ["man", false], two_man: ["man", false], cover0: ["man", true], mike_blitz: ["man", true],
  fire_zone: ["zone", true], edge_blitz: ["zone", true], prevent: ["zone", false],
};

function defense(key: string, pkg: "base" | "nickel" | "dime" = "base") {
  const [coverage, blitz] = COVERAGE[key];
  return { package: key === "prevent" ? "dime" : pkg, coverage, blitz, play: key };
}

/** A completed pass on `play` to `target`, against `call`. */
function passPlay(play: string, call: string, target = pid(H, "WR"), yards?: number): PlaybackPlay {
  const depth = DEPTH[play];
  const air = AIR[depth];
  const gain = yards ?? air + 3;
  const pkg = call === "prevent" ? "dime" : "base";
  return makePlay({
    call: { type: "pass", depth, play }, defense: defense(call, pkg),
    personnel: { ...makePlay().personnel!, ...(pkg === "dime" ? dimePersonnel() : {}) },
    result: { type: "pass", yards: gain, result: "complete" },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth },
             { t: "pass", qb: pid(H, "QB"), target, result: "complete", air, yards: gain },
             { t: "tackle", by: [pid(A, "SS")] }],
  });
}

function dimePersonnel() {
  const d = (p: "DE" | "DT" | "MLB" | "CB" | "FS" | "SS", n = 0) => pid(A, p, n);
  return { defense: [d("DE"), d("DE", 1), d("DT"), d("DT", 1), d("MLB"), d("CB"), d("CB", 1),
                     d("CB", 2), d("CB", 3), d("FS"), d("SS")], package: "dime" as const };
}

function runPlay(play: string, call = "cover3", yards = 5): PlaybackPlay {
  const direction = ["outside_zone", "toss"].includes(play) ? "outside" : "inside";
  return makePlay({
    call: { type: "run", direction, play }, defense: defense(call),
    result: { type: "run", yards },
    events: [{ t: "handoff", to: pid(H, "RB"), direction },
             { t: "rush", player: pid(H, "RB"), yards }, { t: "tackle", by: [pid(A, "MLB")] }],
  });
}

const timelineOf = (play: PlaybackPlay) => choreograph({ ...play, n: 3 }, playback).timeline;
const role = (t: PlayTimeline, side: "offense" | "defense", r: string): TimelinePlayer =>
  t.players.find((p) => p.side === side && p.role === r)!;
/** Play coordinates at `t`: yards downfield of the line, yards toward the offense's right. */
function uv(t: PlayTimeline, p: TimelinePlayer, at: number) {
  const { x, y } = positionAt(p.path, at);
  return { u: (x - t.los!) * t.direction, v: (y - WIDTH / 2) * t.direction };
}
const momentAt = (t: PlayTimeline, kind: string) => t.moments.find((m) => m.kind === kind)!.t;

function expectSound(t: PlayTimeline) {
  expect(t.players).toHaveLength(22);
  for (const p of t.players) {
    for (let i = 0; i < p.path.length; i++) {
      const k = p.path[i];
      expect(k.x).toBeGreaterThanOrEqual(0);
      expect(k.x).toBeLessThanOrEqual(LENGTH);
      expect(k.y).toBeGreaterThanOrEqual(0);
      expect(k.y).toBeLessThanOrEqual(WIDTH);
      if (i > 0) expect(k.t).toBeGreaterThan(p.path[i - 1].t);
    }
    // Everyone is set until the snap.
    expect(positionAt(p.path, SNAP - 0.01)).toEqual(positionAt(p.path, 0));
  }
}

function ballEndX(t: PlayTimeline): number {
  const byId = new Map(t.players.map((p) => [p.id, p]));
  return ballAt(t, t.duration, (id, at) => handsAt(byId.get(id)!, at))[0];
}

describe("the assignment tables", () => {
  it("cover every named play and call, with known routes", () => {
    expect(Object.keys(OFFENSE_PLANS).sort()).toEqual([...OFFENSE_KEYS].sort());
    expect(Object.keys(DEFENSE_PLANS).sort()).toEqual([...DEFENSE_KEYS].sort());
    for (const plan of Object.values(OFFENSE_PLANS)) {
      for (const route of Object.values(plan.routes ?? {})) expect(ROUTES[route]).toBeDefined();
      expect(!!plan.scheme && !!plan.routes).toBe(false);
    }
    for (const key of Object.keys(DEPTH)) expect(OFFENSE_PLANS[key].routes).toBeDefined();
  });
});

describe("every named play against every call", () => {
  it.each(Object.keys(DEPTH))("%s completes soundly against each defense", (play) => {
    for (const call of DEFENSE_KEYS) {
      const t = timelineOf(passPlay(play, call));
      expectSound(t);
      expect(ballEndX(t)).toBeCloseTo(fieldX(30 + AIR[DEPTH[play]] + 3, 1), -0.3);
    }
  });

  it.each(["inside_zone", "power", "counter", "draw", "outside_zone", "toss"])(
    "%s gains the recorded yards soundly against each defense", (play) => {
      for (const call of DEFENSE_KEYS) {
        const t = timelineOf(runPlay(play, call, 7));
        expectSound(t);
        expect(ballEndX(t)).toBeCloseTo(fieldX(37, 1), -0.2);
        expect(t.moments.map((m) => m.kind)).toContain("handoff");
      }
    });
});

describe("formations", () => {
  it("lines the quarterback up under center or in the gun, and snaps it to him there", () => {
    const gun = timelineOf(passPlay("smash", "cover2"));
    expect(uv(gun, role(gun, "offense", "QB"), 0).u).toBeCloseTo(-5);
    expect(gun.ball[1]).toMatchObject({ kind: "flight", from: SNAP });
    const under = timelineOf(passPlay("flood", "cover2"));
    expect(uv(under, role(under, "offense", "QB"), 0).u).toBeCloseTo(-1.2);
    expect(under.ball[1]).toMatchObject({ kind: "held", from: SNAP });
    const iform = timelineOf(runPlay("power"));
    expect(uv(iform, role(iform, "offense", "RB"), 0).u).toBeCloseTo(-7.5);
  });
});

describe("routes", () => {
  it("the target's route is stretched to the recorded air yards", () => {
    const t = timelineOf(passPlay("four_verts", "cover3", pid(H, "WR")));
    const catchT = momentAt(t, "catch");
    expect(uv(t, role(t, "offense", "X"), catchT).u).toBeCloseTo(30, 0);
  });

  it("the others run the play's routes: Smash's slot runs the corner, its outside men sit", () => {
    const t = timelineOf(passPlay("smash", "cover2", pid(H, "WR")));
    const at = momentAt(t, "catch");
    const slot = role(t, "offense", "SLOT");
    const start = uv(t, slot, 0);
    const corner = uv(t, slot, at + 0.3);
    expect(corner.u).toBeGreaterThan(14);
    expect(Math.abs(corner.v)).toBeGreaterThan(Math.abs(start.v)); // broke toward the sideline
    const z = uv(t, role(t, "offense", "Z"), at + 1);
    expect(z.u).toBeLessThan(7); // a hitch
  });

  it("receivers the play has blocking stay in", () => {
    const t = timelineOf(passPlay("four_verts", "cover3"));
    const rb = role(t, "offense", "RB");
    expect(uv(t, rb, t.duration).u).toBeLessThan(0);
    expect(rb.poses.map((p) => p.pose)).toContain("block");
  });
});

describe("run schemes", () => {
  it("Power pulls the backside guard across the formation to lead through the hole", () => {
    const t = timelineOf(runPlay("power", "cover3", 6));
    const pulled = ["LG", "RG"].map((r) => role(t, "offense", r)).find((g) => {
      const a = uv(t, g, 0).v;
      const b = uv(t, g, SNAP + 1.4).v;
      return Math.sign(a) !== Math.sign(b);
    });
    expect(pulled).toBeDefined();
    expect(uv(t, pulled!, SNAP + 1.4).u).toBeGreaterThan(0);
  });

  it("Counter pulls a guard and a tackle", () => {
    const t = timelineOf(runPlay("counter", "cover3", 6));
    const crossers = ["LG", "RG", "LT", "RT"].map((r) => role(t, "offense", r))
      .filter((p) => Math.sign(uv(t, p, 0).v) !== Math.sign(uv(t, p, SNAP + 1.4).v));
    expect(crossers).toHaveLength(2);
  });

  it("Toss pitches the ball to the back; zone runs hand it off", () => {
    const toss = timelineOf(runPlay("toss"));
    expect(toss.moments.find((m) => m.kind === "handoff")!.text).toMatch(/^Pitch to/);
    expect(toss.ball.filter((b) => b.kind === "flight")).toHaveLength(1);
    const zone = timelineOf(runPlay("inside_zone"));
    expect(zone.ball.filter((b) => b.kind === "flight")).toHaveLength(0);
  });

  it("Outside runs bounce wide; inside runs hit the line between the tackles", () => {
    const wide = timelineOf(runPlay("outside_zone", "cover3", 6));
    const inside = timelineOf(runPlay("inside_zone", "cover3", 6));
    const atLine = (t: PlayTimeline) => {
      const rb = role(t, "offense", "RB");
      for (let s = SNAP; s < t.duration; s += 0.05) if (uv(t, rb, s).u >= 0) return Math.abs(uv(t, rb, s).v);
      return 0;
    };
    expect(atLine(wide)).toBeGreaterThan(5);
    expect(atLine(inside)).toBeLessThan(4);
  });
});

describe("passing extras", () => {
  it("play action fakes the handoff first; the boot rolls the quarterback away from it", () => {
    const t = timelineOf(passPlay("pa_boot", "cover3", pid(H, "TE")));
    expect(t.moments.map((m) => m.text)).toContain("Play-action fake");
    const qb = role(t, "offense", "QB");
    const fake = uv(t, qb, momentAt(t, "handoff"));
    const rolled = uv(t, qb, momentAt(t, "throw"));
    expect(Math.sign(rolled.v)).toBe(-Math.sign(fake.v));
    expect(Math.abs(rolled.v)).toBeGreaterThan(4);
  });

  it("a screen lets the rush in and sends the line out to block for the back", () => {
    const t = timelineOf(passPlay("rb_screen", "cover0", pid(H, "RB")));
    const thrown = momentAt(t, "throw");
    const qb = uv(t, role(t, "offense", "QB"), thrown);
    const ends = ["LDE", "RDE"].map((r) => uv(t, role(t, "defense", r), thrown));
    expect(Math.min(...ends.map((e) => Math.hypot(e.u - qb.u, e.v - qb.v)))).toBeLessThan(4);
    const linemen = ["LG", "C", "RG"].map((r) => uv(t, role(t, "offense", r), thrown + 0.7));
    expect(linemen.every((l) => l.u > 0)).toBe(true);
  });
});

describe("defensive calls", () => {
  it("zone shells drop to their landmarks: Cover 3 corners bail deep, Cover 2 corners sit in the flats", () => {
    const three = timelineOf(passPlay("dig", "cover3"));
    const two = timelineOf(passPlay("dig", "cover2"));
    const at = (t: PlayTimeline) => uv(t, role(t, "defense", "CB1"), momentAt(t, "throw"));
    expect(at(three).u).toBeGreaterThan(12);
    expect(at(two).u).toBeLessThan(8);
    const safety = uv(two, role(two, "defense", "FS"), momentAt(two, "throw"));
    expect(safety.u).toBeGreaterThan(14);
  });

  it("man coverage trails its man", () => {
    const t = timelineOf(passPlay("slants", "cover1", pid(H, "TE")));
    const cb = role(t, "defense", "CB1");
    const x = role(t, "offense", "X");
    for (let s = SNAP + 0.5; s < momentAt(t, "catch"); s += 0.25) {
      const a = positionAt(cb.path, s);
      const b = positionAt(x.path, s);
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(4);
    }
  });

  it("blitzers rush the quarterback; Fire Zone drops an end into coverage", () => {
    const mike = timelineOf(passPlay("dig", "mike_blitz"));
    const qb = uv(mike, role(mike, "offense", "QB"), momentAt(mike, "throw"));
    const backer = uv(mike, role(mike, "defense", "MIKE"), momentAt(mike, "throw"));
    expect(Math.hypot(qb.u - backer.u, qb.v - backer.v)).toBeLessThan(3);

    const fire = timelineOf(passPlay("dig", "fire_zone"));
    expect(uv(fire, role(fire, "defense", "LDE"), momentAt(fire, "throw")).u).toBeGreaterThan(3);
    const will = uv(fire, role(fire, "defense", "WILL"), momentAt(fire, "throw"));
    expect(will.u).toBeLessThan(0);
  });

  it("prevent plays everyone deep, in dime", () => {
    const t = timelineOf(passPlay("hitches", "prevent"));
    expect(t.players.filter((p) => p.side === "defense" && p.position === "CB")).toHaveLength(4);
    const deep = uv(t, role(t, "defense", "FS"), momentAt(t, "throw"));
    expect(deep.u).toBeGreaterThan(20);
  });
});

describe("old play logs", () => {
  it("plays without named calls still choreograph the old way", () => {
    const legacy = passPlay("smash", "cover2");
    const t = timelineOf({ ...legacy, call: { type: "pass", depth: "medium" },
                           defense: { package: "base", coverage: "zone", blitz: true } });
    expectSound(t);
    expect(uv(t, role(t, "offense", "QB"), 0).u).toBeCloseTo(-1.2); // under center
  });

  it("an event list without named plays is unchanged in shape", () => {
    const events: PlayEvent[] = runPlay("power").events;
    const t = timelineOf(makePlay({ result: { type: "run", yards: 5 }, events }));
    expectSound(t);
  });
});
