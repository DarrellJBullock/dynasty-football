import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { makePlayerDetail, opponent, team } from "@/test/fixtures";
import { CommissionerTools } from "./CommissionerTools";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { movePlayer: vi.fn(), setContract: vi.fn(), updatePlayer: vi.fn() } };
});
const mocked = vi.mocked(api);

const player = makePlayerDetail({ id: 41, first_name: "Keegan", last_name: "Quarles", team_id: team.id,
  contract: { start_year: 2026, years: 4, end_year: 2029, salary: 20_000_000, signing_bonus: 0 } });
const teams = [team, opponent];

beforeEach(() => vi.clearAllMocks());

describe("CommissionerTools", () => {
  it("moves a player to another team", async () => {
    mocked.movePlayer.mockResolvedValue({ ...player, team_id: opponent.id });
    render(<CommissionerTools player={player} teams={teams} />);
    const moveButton = screen.getByRole("button", { name: "Move player" });
    expect(moveButton).toBeDisabled(); // (he's already there)
    await userEvent.selectOptions(screen.getByLabelText("Move to"), opponent.full_name);
    await userEvent.click(moveButton);
    expect(mocked.movePlayer).toHaveBeenCalledWith(41, opponent.id);
    expect(await screen.findByRole("status")).toHaveTextContent(`Moved to ${opponent.full_name}.`);
    expect(refresh).toHaveBeenCalled();
  });

  it("releases him to free agency", async () => {
    mocked.movePlayer.mockResolvedValue({ ...player, team_id: null, contract: null });
    render(<CommissionerTools player={player} teams={teams} />);
    await userEvent.selectOptions(screen.getByLabelText("Move to"), "Free agency");
    await userEvent.click(screen.getByRole("button", { name: "Move player" }));
    expect(mocked.movePlayer).toHaveBeenCalledWith(41, null);
    expect(await screen.findByRole("status")).toHaveTextContent("Moved to free agency.");
  });

  it("rewrites his contract", async () => {
    mocked.setContract.mockResolvedValue({ ...player,
      contract: { start_year: 2026, years: 3, end_year: 2028, salary: 4_000_000, signing_bonus: 0 } });
    render(<CommissionerTools player={player} teams={teams} />);
    const salary = screen.getByLabelText("Salary ($M a season)");
    await userEvent.clear(salary);
    await userEvent.type(salary, "4");
    await userEvent.selectOptions(screen.getByLabelText("Years"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Save contract" }));
    expect(mocked.setContract).toHaveBeenCalledWith(41, 4_000_000, 3);
    expect(await screen.findByRole("status")).toHaveTextContent("through 2028");
  });

  it("shows why an edit was refused", async () => {
    mocked.movePlayer.mockRejectedValue(new Error("The Albuquerque Roadrunners' roster is full (53 players)."));
    render(<CommissionerTools player={player} teams={teams} />);
    await userEvent.selectOptions(screen.getByLabelText("Move to"), opponent.full_name);
    await userEvent.click(screen.getByRole("button", { name: "Move player" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("roster is full");
  });

  it("edits his ratings in a dialog", async () => {
    render(<CommissionerTools player={player} teams={teams} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit player" }));
    const dialog = screen.getByRole("dialog", { name: "Edit player" });
    expect(within(dialog).getByDisplayValue("Keegan")).toBeInTheDocument();
  });

  it("has no contract for a free agent", () => {
    render(<CommissionerTools player={{ ...player, team_id: null, contract: null }} teams={teams} />);
    expect(screen.getByText(/A free agent has no contract/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save contract" })).not.toBeInTheDocument();
  });
});
