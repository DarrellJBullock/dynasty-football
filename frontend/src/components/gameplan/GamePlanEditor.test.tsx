import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { GamePlan, Playbook } from "@/lib/types";
import { team } from "@/test/fixtures";
import { GamePlanEditor } from "./GamePlanEditor";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { saveGamePlan: vi.fn(), resetGamePlan: vi.fn() } };
});
const mocked = vi.mocked(api);

const play = (key: string, name: string, category: string) => ({
  key, name, category, formation: "Shotgun", kind: "pass", description: `${name} description`,
  direction: null, depth: null, play_action: false, targets: null,
}) as Playbook["offense"][number];
const call = (key: string, name: string, category: string) => ({
  key, name, category, shell: "two_high", coverage: "zone", blitz: false,
  description: `${name} description`, package: null,
}) as Playbook["defense"][number];

const playbook: Playbook = {
  offense: [play("inside_zone", "Inside Zone", "run"), play("toss", "Toss", "run"),
    play("four_verts", "Four Verticals", "deep"), play("kneel", "Kneel", "special")],
  defense: [call("cover3", "Cover 3", "zone"), call("cover1", "Cover 1", "man"),
    call("fire_zone", "Fire Zone", "pressure")],
};
const plan: GamePlan = {
  team_id: team.id, custom: false,
  offense: ["four_verts", "inside_zone", "toss"], defense: ["cover1", "cover3", "fire_zone"],
  tendencies: { pass_rate: 0, blitz: 0 }, suggested: { pass_rate: 0, blitz: 1 },
  offense_choices: ["four_verts", "inside_zone", "toss"], defense_choices: ["cover1", "cover3", "fire_zone"],
  tendency_labels: { pass_rate: "Run or pass", blitz: "Blitzing" },
  required: [{ side: "offense", label: "a deep pass", keys: ["four_verts"] },
    { side: "defense", label: "a man coverage without a blitz", keys: ["cover1"] }],
};

beforeEach(() => vi.clearAllMocks());

describe("GamePlanEditor", () => {
  it("shows the plan's plays by group and the roster's suggestions", () => {
    render(<GamePlanEditor initial={plan} playbook={playbook} team={team} />);
    const runs = screen.getByRole("group", { name: "Runs" });
    expect(within(runs).getByRole("checkbox", { name: /Inside Zone/ })).toBeChecked();
    expect(screen.queryByRole("checkbox", { name: /Kneel/ })).not.toBeInTheDocument(); // not a choice
    expect(screen.getByText("Suggested for your roster")).toBeInTheDocument();
    const blitzing = screen.getByRole("group", { name: "Blitzing" });
    expect(within(blitzing).getByRole("radio", { name: "Usual" })).toBeChecked();
    expect(blitzing).toHaveTextContent("Suggested for your roster: More");
  });

  it("says what a plan must keep, and won't save without it", async () => {
    render(<GamePlanEditor initial={plan} playbook={playbook} team={team} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Four Verticals/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("The plan needs a deep pass.");
    expect(screen.getByRole("button", { name: "Save game plan" })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Four Verticals/ }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("saves the plays and tendencies, then can reset to the suggested plan", async () => {
    const custom = { ...plan, custom: true, offense: ["four_verts", "inside_zone"],
      tendencies: { pass_rate: 2, blitz: 0 } };
    mocked.saveGamePlan.mockResolvedValue(custom);
    mocked.resetGamePlan.mockResolvedValue(plan);
    render(<GamePlanEditor initial={plan} playbook={playbook} team={team} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Toss/ }));
    await userEvent.click(within(screen.getByRole("group", { name: "Run or pass" }))
      .getByRole("radio", { name: "Much more" }));
    await userEvent.click(screen.getByRole("button", { name: "Save game plan" }));
    expect(mocked.saveGamePlan).toHaveBeenCalledWith(team.id, {
      offense: ["four_verts", "inside_zone"], defense: ["cover1", "cover3", "fire_zone"],
      tendencies: { pass_rate: 2, blitz: 0 } });
    expect(await screen.findByRole("status")).toHaveTextContent("Game plan saved.");
    expect(screen.getByText("Your plan")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Reset to the suggested plan" }));
    expect(mocked.resetGamePlan).toHaveBeenCalledWith(team.id);
    expect(await screen.findByRole("status")).toHaveTextContent("Back to the plan for your roster.");
    expect(screen.getByRole("checkbox", { name: /Toss/ })).toBeChecked();
  });

  it("shows the server's reasons", async () => {
    mocked.saveGamePlan.mockRejectedValue(new ApiError(422, "The plan needs an outside run."));
    render(<GamePlanEditor initial={plan} playbook={playbook} team={team} />);
    await userEvent.click(screen.getByRole("button", { name: "Save game plan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The plan needs an outside run.");
  });
});
