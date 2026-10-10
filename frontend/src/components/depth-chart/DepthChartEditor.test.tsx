import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { DepthChart } from "@/lib/types";
import { makeDepthChart, makePlayer } from "@/test/fixtures";
import { DepthChartEditor } from "./DepthChartEditor";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      setDepthSlot: vi.fn(),
      resetDepthSlot: vi.fn(),
      resetDepthChart: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

const quarles = makePlayer({ first_name: "Keegan", last_name: "Quarles", position: "QB", overall: 82 });
const sterling = makePlayer({ first_name: "Kobe", last_name: "Sterling", position: "QB", overall: 62 });
const fonoti = makePlayer({ first_name: "Carter", last_name: "Fonoti", position: "QB", overall: 61, injury_status: "out" });
const corner = makePlayer({ first_name: "Terrell", last_name: "Stroud", position: "CB", overall: 86 });
const safety = makePlayer({ first_name: "Reed", last_name: "Hale", position: "FS", overall: 70 });

function initialChart(): DepthChart {
  return makeDepthChart({
    QB: { players: [quarles, sterling, fonoti], starter_ids: [quarles.id] },
    CB: { players: [corner], starter_ids: [corner.id] },
    FS: { players: [safety], starter_ids: [safety.id] },
  });
}

function rows() {
  return screen.getAllByTestId("depth-row").map((r) => r.getAttribute("aria-label"));
}

/** Echo the requested order back as the server would, with the first player starting. */
function echoServer(base: DepthChart, overrides: Partial<DepthChart["team"]["ratings"]> = {}) {
  mocked.setDepthSlot.mockImplementation(async (_team, slot, ids) => {
    const all = new Map(base.slots.flatMap((s) => s.players).map((p) => [p.id, p]));
    return {
      team: { ...base.team, ratings: { ...base.team.ratings, ...overrides } },
      slots: base.slots.map((s) =>
        s.slot === slot
          ? { ...s, customized: true, players: ids.map((id) => all.get(id)!), starter_ids: ids.slice(0, s.starters) }
          : s,
      ),
    };
  });
}

beforeEach(() => vi.clearAllMocks());

describe("DepthChartEditor", () => {
  it("shows the quarterback depth chart with starter and injury notes", () => {
    render(<DepthChartEditor initialChart={initialChart()} />);
    expect(screen.getByRole("heading", { name: "Quarterback" })).toBeInTheDocument();
    expect(rows()).toEqual(["1. Keegan Quarles", "2. Kobe Sterling", "3. Carter Fonoti"]);
    const first = screen.getAllByTestId("depth-row")[0];
    expect(within(first).getByText("Starter")).toBeInTheDocument();
    expect(within(screen.getAllByTestId("depth-row")[2]).getByText("Out")).toBeInTheDocument();
  });

  it("moves a player up, saves the new order, and shows updated ratings", async () => {
    const chart = initialChart();
    echoServer(chart, { offense: 70, overall: 75 });
    render(<DepthChartEditor initialChart={chart} />);

    await userEvent.click(screen.getByRole("button", { name: "Move Kobe Sterling up" }));

    expect(rows()).toEqual(["1. Kobe Sterling", "2. Keegan Quarles", "3. Carter Fonoti"]);
    expect(mocked.setDepthSlot).toHaveBeenCalledWith(1, "QB", [sterling.id, quarles.id, fonoti.id]);
    await waitFor(() => expect(screen.getByTitle("Offense 70")).toBeInTheDocument());
    expect(screen.getByTitle("Team OVR 75")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset to OVR order" })).toBeEnabled();
  });

  it("reverts the order and shows an error when saving fails", async () => {
    mocked.setDepthSlot.mockRejectedValue(new Error("players not on this roster: 9"));
    render(<DepthChartEditor initialChart={initialChart()} />);

    await userEvent.click(screen.getByRole("button", { name: "Move Keegan Quarles down" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("players not on this roster");
    expect(rows()).toEqual(["1. Keegan Quarles", "2. Kobe Sterling", "3. Carter Fonoti"]);
  });

  it("disables moving the top player up and the bottom player down", () => {
    render(<DepthChartEditor initialChart={initialChart()} />);
    expect(screen.getByRole("button", { name: "Move Keegan Quarles up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Carter Fonoti down" })).toBeDisabled();
  });

  it("switches units and slots", async () => {
    render(<DepthChartEditor initialChart={initialChart()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Defense" }));
    expect(screen.getByRole("heading", { name: "Defensive End" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Free Safety/ }));
    expect(screen.getByRole("heading", { name: "Free Safety" })).toBeInTheDocument();
    expect(rows()).toEqual(["1. Reed Hale"]);
  });

  it("cross-lists a player from another position and can remove them again", async () => {
    const chart = initialChart();
    echoServer(chart);
    render(<DepthChartEditor initialChart={chart} />);
    await userEvent.click(screen.getByRole("tab", { name: "Defense" }));
    await userEvent.click(screen.getByRole("button", { name: /Free Safety/ }));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Add a player to FS" }), String(corner.id));
    expect(mocked.setDepthSlot).toHaveBeenLastCalledWith(1, "FS", [safety.id, corner.id]);
    await waitFor(() => expect(rows()).toEqual(["1. Reed Hale", "2. Terrell Stroud"]));

    // Natural safeties can't be removed (they'd be re-added); cross-listed players can.
    expect(screen.queryByRole("button", { name: "Remove Reed Hale from FS" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove Terrell Stroud from FS" }));
    expect(mocked.setDepthSlot).toHaveBeenLastCalledWith(1, "FS", [safety.id]);
  });

  it("resets a customized slot and the whole chart", async () => {
    const chart = initialChart();
    chart.slots = chart.slots.map((s) => (s.slot === "QB" ? { ...s, customized: true } : s));
    mocked.resetDepthSlot.mockResolvedValue(initialChart());
    mocked.resetDepthChart.mockResolvedValue(initialChart());
    render(<DepthChartEditor initialChart={chart} />);

    await userEvent.click(screen.getByRole("button", { name: "Reset to OVR order" }));
    expect(mocked.resetDepthSlot).toHaveBeenCalledWith(1, "QB");
    await waitFor(() => expect(screen.getByRole("button", { name: "Reset to OVR order" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Reset all to OVR order" })).toBeDisabled();
  });

  it("flags starting slots with no available starter", async () => {
    const chart = makeDepthChart({ QB: { players: [fonoti], starter_ids: [] } });
    render(<DepthChartEditor initialChart={chart} />);
    expect(within(screen.getByRole("navigation", { name: "Positions" })).getAllByText("No starter").length).toBeGreaterThan(0);
    expect(screen.getByText("Injured — not starting")).toBeInTheDocument();
  });
});
