import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { choreographGame } from "@/components/field/playback/choreograph";
import { makePlay, makePlayback, pid } from "@/test/fixtures";
import { BroadcastOverlay } from "./BroadcastOverlay";

const H = 1;
const playback = makePlayback([
  // The drive so far (the score going in).
  makePlay({ clock: "2:40", quarter: 4, score: { home: 17, away: 20 }, result: { type: "run", yards: 3 },
    events: [{ t: "rush", player: pid(H, "RB"), yards: 3 }] }),
  makePlay({ clock: "2:05", quarter: 4, seconds: 6, timeouts: { home: 2, away: 1 },
    down: 3, distance: 6, ball_on: 30, score: { home: 17, away: 20 },
    result: { type: "run", yards: 9, first_down: true },
    events: [{ t: "handoff", to: pid(H, "RB"), direction: "inside" },
             { t: "rush", player: pid(H, "RB"), yards: 9 }, { t: "tackle", by: [pid(2, "MLB")] }] }),
  makePlay({ clock: "1:20", quarter: 4, seconds: 5, timeouts: { home: 2, away: 1 },
    down: 1, distance: 10, ball_on: 85, score: { home: 23, away: 20 },
    result: { type: "pass", yards: 15, result: "complete", touchdown: true },
    events: [{ t: "dropback", qb: pid(H, "QB"), depth: "medium" },
             { t: "pass", qb: pid(H, "QB"), target: pid(H, "TE"), result: "complete", air: 12, yards: 15 }] }),
]);
const [, first, second] = choreographGame(playback);

function show(index: number, time: number) {
  const { timeline } = index === 1 ? first : second;
  return render(<BroadcastOverlay playback={playback} index={index} timeline={timeline} time={time} />);
}

describe("BroadcastOverlay", () => {
  it("shows the score, the possession, timeouts, the quarter, the clock and the down", () => {
    show(1, 0);
    const bug = screen.getByRole("group", { name: "Score bug" });
    expect(within(bug).getByTestId("bug-HFD")).toHaveTextContent("HFD●17");
    expect(within(bug).getByTestId("bug-ABQ")).toHaveTextContent("ABQ20");
    expect(within(bug).getByLabelText("2 timeouts")).toBeInTheDocument();
    expect(within(bug).getByLabelText("1 timeouts")).toBeInTheDocument();
    expect(bug).toHaveTextContent("4th2:05");
    expect(within(bug).getByTestId("down")).toHaveTextContent("3rd & 6");
    expect(bug).toHaveTextContent("at HFD 30");
    expect(within(bug).getByLabelText(/^Play clock \d+$/)).toBeInTheDocument();
  });

  it("runs the game clock through the play and drops the play clock at the snap", () => {
    const { rerender } = show(1, 1.5);
    expect(screen.queryByLabelText(/^Play clock/)).not.toBeInTheDocument();
    const mid = screen.getByTestId("game-clock").textContent;
    expect(mid).not.toBe("2:05");
    rerender(<BroadcastOverlay playback={playback} index={1} timeline={first.timeline} time={first.timeline.duration} />);
    expect(screen.getByTestId("game-clock")).toHaveTextContent("1:59"); // 6 seconds ran
  });

  it("puts the points up at the touchdown, with a banner", () => {
    const touchdown = second.timeline.moments.find((m) => m.kind === "touchdown")!.t;
    const { rerender } = show(2, touchdown - 0.2);
    expect(screen.getByTestId("bug-HFD")).toHaveTextContent("17");
    expect(screen.queryByTestId("banner")).not.toBeInTheDocument();
    rerender(<BroadcastOverlay playback={playback} index={2} timeline={second.timeline} time={touchdown + 0.1} />);
    expect(screen.getByTestId("bug-HFD")).toHaveTextContent("23");
    expect(screen.getByTestId("banner")).toHaveTextContent("Touchdown");
  });

  it("calls out a first down at the tackle", () => {
    const tackle = first.timeline.moments.find((m) => m.kind === "tackle")!.t;
    show(1, tackle + 0.5);
    expect(screen.getByTestId("banner")).toHaveTextContent("First down");
  });

  it("leaves out timeouts for old games that didn't record them", () => {
    const old = { ...playback, plays: playback.plays.map((p) => ({ ...p, timeouts: null })) };
    render(<BroadcastOverlay playback={old} index={1} timeline={first.timeline} time={0} />);
    expect(screen.queryByLabelText(/timeouts$/)).not.toBeInTheDocument();
  });
});

describe("stat overlays", () => {
  const whistleOf = (t: typeof second.timeline) => t.moments.find((m) => m.kind === "whistle")!.t;

  it("after a touchdown pass: the passer's line, and on the last play the final stats", () => {
    const done = whistleOf(second.timeline) + 0.5;
    const { rerender } = show(2, whistleOf(second.timeline) - 0.5);
    expect(screen.queryByTestId("lower-third")).not.toBeInTheDocument();
    rerender(<BroadcastOverlay playback={playback} index={2} timeline={second.timeline} time={done} />);
    const lower = screen.getByRole("note", { name: "Player stats" });
    expect(lower).toHaveTextContent(/^#\d+H\. QB0QB1\/1, 15 yds, 1 TD$/);
    const final = screen.getByRole("note", { name: "Final stats" });
    expect(final).toHaveTextContent("HFD 23");
    expect(within(final).getByRole("row", { name: /Total yards/ })).toHaveTextContent("0Total yards27");
    expect(screen.queryByTestId("drive-summary")).not.toBeInTheDocument(); // the final card says it
    // Not during a replay.
    rerender(<BroadcastOverlay playback={playback} index={2} timeline={second.timeline} time={done} replay />);
    expect(screen.queryByTestId("lower-third")).not.toBeInTheDocument();
    expect(screen.queryByTestId("break-card")).not.toBeInTheDocument();
  });

  it("sums up a drive when it ends", () => {
    const drive = makePlayback([
      makePlay({ ball_on: 25, elapsed: 34, result: { type: "run", yards: 6 },
        events: [{ t: "rush", player: pid(H, "RB"), yards: 6 }] }),
      makePlay({ down: 4, distance: 4, ball_on: 31, elapsed: 12, personnel: null, defense: null,
        result: { type: "punt" },
        events: [{ t: "punt", punter: pid(H, "P"), yards: 44, touchback: false, fair_catch: true, return: 0 }] }),
      makePlay({ side: "away", offense: "ABQ", ball_on: 25, result: { type: "run", yards: 2 },
        events: [{ t: "rush", player: pid(2, "RB"), yards: 2 }] }),
    ]);
    const [, punt] = choreographGame(drive);
    render(<BroadcastOverlay playback={drive} index={1} timeline={punt.timeline}
      time={whistleOf(punt.timeline) + 0.5} />);
    expect(screen.getByRole("note", { name: "Drive summary" }))
      .toHaveTextContent("HFD drive2 plays · 6 yds · 0:46 · Punt");
    expect(screen.queryByTestId("break-card")).not.toBeInTheDocument();
  });
});
