import { describe, expect, it } from "vitest";
import { makeDepthChart, makePlayer } from "@/test/fixtures";
import { addablePlayers, moveItem, replaceSlotOrder, rowStatus, startingSlots } from "./depthChart";

describe("moveItem", () => {
  it("moves an item up and down", () => {
    expect(moveItem(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(moveItem(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
  });

  it("clamps out-of-range targets and ignores bad sources", () => {
    expect(moveItem(["a", "b"], 0, 9)).toEqual(["b", "a"]);
    expect(moveItem(["a", "b"], 5, 0)).toEqual(["a", "b"]);
  });

  it("does not mutate the input", () => {
    const items = ["a", "b"];
    moveItem(items, 0, 1);
    expect(items).toEqual(["a", "b"]);
  });
});

describe("rowStatus", () => {
  const qb1 = makePlayer({ position: "QB", overall: 85 });
  const qb2 = makePlayer({ position: "QB", overall: 70, injury_status: "out" });

  it("marks fielded starters", () => {
    const chart = makeDepthChart({ QB: { players: [qb1, qb2], starter_ids: [qb1.id] } });
    const slot = chart.slots.find((s) => s.slot === "QB")!;
    expect(rowStatus(qb1, 0, slot, startingSlots(chart))).toEqual({ kind: "starter" });
    expect(rowStatus(qb2, 1, slot, startingSlots(chart))).toEqual({ kind: "backup" });
  });

  it("explains an injured player in the starter window", () => {
    const chart = makeDepthChart({ QB: { players: [qb2, qb1], starter_ids: [qb1.id] } });
    const slot = chart.slots.find((s) => s.slot === "QB")!;
    expect(rowStatus(qb2, 0, slot, startingSlots(chart))).toEqual({ kind: "injured" });
  });

  it("explains a player who starts at another slot", () => {
    const ot = makePlayer({ position: "OT", overall: 80 });
    const og = makePlayer({ position: "OG", overall: 70 });
    const chart = makeDepthChart({
      OT: { players: [ot], starter_ids: [ot.id] },
      OG: { players: [ot, og], starter_ids: [og.id] },
    });
    const slot = chart.slots.find((s) => s.slot === "OG")!;
    expect(rowStatus(ot, 0, slot, startingSlots(chart))).toEqual({ kind: "starting-elsewhere", slot: "OT" });
  });
});

describe("addablePlayers / replaceSlotOrder", () => {
  const cb = makePlayer({ position: "CB", overall: 80 });
  const fs = makePlayer({ position: "FS", overall: 75 });
  const chart = makeDepthChart({ CB: { players: [cb] }, FS: { players: [fs] } });

  it("offers rostered players not already listed in the slot", () => {
    const slot = chart.slots.find((s) => s.slot === "FS")!;
    expect(addablePlayers(chart, slot).map((p) => p.id)).toEqual([cb.id]);
  });

  it("replaces one slot's order and marks it customized", () => {
    const next = replaceSlotOrder(chart, "FS", [cb, fs]);
    const slot = next.slots.find((s) => s.slot === "FS")!;
    expect(slot.players).toEqual([cb, fs]);
    expect(slot.customized).toBe(true);
    expect(chart.slots.find((s) => s.slot === "FS")!.players).toEqual([fs]);
  });
});
