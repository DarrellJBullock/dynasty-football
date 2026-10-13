import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { LeagueRules } from "@/lib/types";
import { LeagueRulesPanel } from "./LeagueRulesPanel";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { updateRules: vi.fn() } };
});
const mocked = vi.mocked(api);

const rules: LeagueRules = {
  roster_max: 53, salary_cap: 255_000_000, cap_growth_pct: 0, playoff_seeds: null, seeds: 7, byes: 1,
  seed_choices: [2, 3, 4, 5, 6, 7, 8], season_weeks: 17, max_weeks: 20, locked_reason: null, firing: "auto",
};

beforeEach(() => vi.clearAllMocks());

describe("LeagueRulesPanel", () => {
  it("shows the rules to everyone", () => {
    render(<LeagueRulesPanel leagueId={1} initial={rules} commissioner={false} />);
    const panel = screen.getByRole("region", { name: "League rules" });
    expect(panel).toHaveTextContent("53 players");
    expect(panel).toHaveTextContent("$255M");
    expect(panel).toHaveTextContent("7 per conference, 1 bye (by conference size)");
    expect(panel).toHaveTextContent("17 weeks");
    expect(within(panel).queryByRole("button")).not.toBeInTheDocument();
  });

  it("lets the commissioner change only what they change", async () => {
    mocked.updateRules.mockResolvedValue({ ...rules, roster_max: 50, cap_growth_pct: 3,
      playoff_seeds: 4, seeds: 4, byes: 0 });
    render(<LeagueRulesPanel leagueId={1} initial={rules} commissioner />);
    await userEvent.click(screen.getByRole("button", { name: "Change the rules" }));
    const roster = screen.getByLabelText("Roster size (45–60)");
    await userEvent.clear(roster);
    await userEvent.type(roster, "50");
    const growth = screen.getByLabelText("Cap growth each season (%)");
    await userEvent.clear(growth);
    await userEvent.type(growth, "3");
    await userEvent.selectOptions(screen.getByLabelText("Playoff seeds per conference"), "4");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(mocked.updateRules).toHaveBeenCalledWith(1, { roster_max: 50, cap_growth_pct: 3, playoff_seeds: 4 });
    const panel = screen.getByRole("region", { name: "League rules" });
    expect(await within(panel).findByRole("status")).toHaveTextContent("League log");
    expect(panel).toHaveTextContent("4 per conference, no byes");
    expect(panel).toHaveTextContent("3% a season");
  });

  it("goes back to automatic seeds", async () => {
    mocked.updateRules.mockResolvedValue(rules);
    render(<LeagueRulesPanel leagueId={1} initial={{ ...rules, playoff_seeds: 6, seeds: 6, byes: 2 }} commissioner />);
    await userEvent.click(screen.getByRole("button", { name: "Change the rules" }));
    await userEvent.selectOptions(screen.getByLabelText("Playoff seeds per conference"), "By conference size");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(mocked.updateRules).toHaveBeenCalledWith(1, { playoff_seeds: null });
  });

  it("says why the rules can't change mid-season", () => {
    render(<LeagueRulesPanel leagueId={1} commissioner
      initial={{ ...rules, locked_reason: "League rules change between seasons." }} />);
    expect(screen.getByText("League rules change between seasons.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change the rules" })).not.toBeInTheDocument();
  });

  it("shows why a change was refused", async () => {
    mocked.updateRules.mockRejectedValue(new Error("A roster is 45 to 60 players."));
    render(<LeagueRulesPanel leagueId={1} initial={rules} commissioner />);
    await userEvent.click(screen.getByRole("button", { name: "Change the rules" }));
    const weeks = screen.getByLabelText("Regular season (weeks)");
    await userEvent.clear(weeks);
    await userEvent.type(weeks, "12");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(mocked.updateRules).toHaveBeenCalledWith(1, { season_weeks: 12 });
    expect(await screen.findByRole("alert")).toHaveTextContent("45 to 60");
  });

  it("turns firing off", async () => {
    mocked.updateRules.mockResolvedValue({ ...rules, firing: "off" });
    render(<LeagueRulesPanel leagueId={1} initial={rules} commissioner />);
    expect(screen.getByRole("region", { name: "League rules" })).toHaveTextContent("FiringAutomatic");
    await userEvent.click(screen.getByRole("button", { name: "Change the rules" }));
    await userEvent.selectOptions(screen.getByLabelText("Owners fire general managers"), "Off");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(mocked.updateRules).toHaveBeenCalledWith(1, { firing: "off" });
  });
});
