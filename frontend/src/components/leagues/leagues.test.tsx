import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { FranchiseListItem } from "@/lib/types";
import { dashboard, makeSpec, opponent, teamDetail } from "@/test/fixtures";
import { LeagueBuilder } from "./LeagueBuilder";
import { LeaguesHub } from "./LeaguesHub";
import { TeamEditDialog } from "./TeamEditButton";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      leagueTemplate: vi.fn(),
      createLeague: vi.fn(),
      franchises: vi.fn(),
      activateFranchise: vi.fn(),
      deleteLeague: vi.fn(),
      updateTeam: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

beforeEach(() => {
  vi.clearAllMocks();
  mocked.leagueTemplate.mockResolvedValue(makeSpec());
});

describe("LeagueBuilder", () => {
  it("loads a template and creates the league", async () => {
    mocked.createLeague.mockResolvedValue(dashboard.franchise);
    render(<LeagueBuilder />);
    expect(mocked.leagueTemplate).toHaveBeenCalledWith(2, 4, 4);
    await screen.findAllByTestId("builder-team");

    await userEvent.click(screen.getByRole("radio", { name: "Play as City CCC Nick CCC" }));
    await userEvent.click(screen.getByRole("radio", { name: /Start empty/ }));
    await userEvent.click(screen.getByRole("button", { name: "Create league" }));

    expect(mocked.createLeague).toHaveBeenCalledWith(
      expect.objectContaining({ user_team: "CCC", rosters: "empty", name: "Test League" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
    expect(router.refresh).toHaveBeenCalled();
  });

  it("refetches the template when the structure changes and blocks odd totals", async () => {
    render(<LeagueBuilder />);
    await screen.findAllByTestId("builder-team");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Teams per division" }), "3");
    await waitFor(() => expect(mocked.leagueTemplate).toHaveBeenLastCalledWith(2, 4, 3));
    expect(screen.getByTestId("team-total")).toHaveTextContent("24 teams");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Conferences" }), "1");
    await waitFor(() => expect(mocked.leagueTemplate).toHaveBeenLastCalledWith(1, 4, 3));
    // 1 × 3 × 3 = 9 teams: odd, so no template request and creation is blocked.
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Divisions per conference" }), "3");
    expect(screen.getByRole("alert")).toHaveTextContent("even number");
    expect(mocked.leagueTemplate).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("button", { name: "Create league" })).toBeDisabled();
  });

  it("flags duplicate abbreviations and blocks creation", async () => {
    render(<LeagueBuilder />);
    await screen.findAllByTestId("builder-team");
    const abbr = screen.getByRole("textbox", { name: "Abbreviation for City BBB Nick BBB" });
    await userEvent.clear(abbr);
    await userEvent.type(abbr, "aaa");

    expect(abbr).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Abbreviations used twice: AAA.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create league" })).toBeDisabled();
  });

  it("shows server validation errors", async () => {
    mocked.createLeague.mockRejectedValue(new ApiError(422, "user_team ZZZ is not one of the league's teams"));
    render(<LeagueBuilder />);
    await screen.findAllByTestId("builder-team");
    await userEvent.click(screen.getByRole("button", { name: "Create league" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not one of the league's teams");
    expect(router.push).not.toHaveBeenCalled();
  });
});

function franchiseItem(overrides: Partial<FranchiseListItem>): FranchiseListItem {
  return { ...dashboard.franchise, is_active: false, team_count: 32, ...overrides };
}

describe("LeaguesHub", () => {
  const active = franchiseItem({ id: 1, name: "Ironclads Dynasty", is_active: true });
  const other = franchiseItem({
    id: 2, name: "Krakens Dynasty", team: opponent, team_count: 6,
    league: { id: 9, name: "Harbor Coast League", abbreviation: "HCL", salary_cap: 200_000_000 },
  });

  it("switches franchises", async () => {
    mocked.activateFranchise.mockResolvedValue(other);
    render(<LeaguesHub initialFranchises={[active, other]} />);
    const card = screen.getByRole("listitem", { name: "Krakens Dynasty" });
    expect(within(card).getByText(/Harbor Coast League · 6 teams/)).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "Switch to this franchise" }));
    expect(mocked.activateFranchise).toHaveBeenCalledWith(2);
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
  });

  it("only lets inactive leagues be deleted, with confirmation", async () => {
    mocked.deleteLeague.mockResolvedValue(undefined);
    render(<LeaguesHub initialFranchises={[active, other]} />);
    const activeCard = screen.getByRole("listitem", { name: "Ironclads Dynasty" });
    expect(within(activeCard).queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();

    const card = screen.getByRole("listitem", { name: "Krakens Dynasty" });
    await userEvent.click(within(card).getByRole("button", { name: "Delete Harbor Coast League" }));
    expect(within(card).getByText(/Delete Harbor Coast League and all its players/)).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Delete league" }));

    expect(mocked.deleteLeague).toHaveBeenCalledWith(9);
    await waitFor(() =>
      expect(screen.queryByRole("listitem", { name: "Krakens Dynasty" })).not.toBeInTheDocument());
  });

  it("shows errors from the server", async () => {
    mocked.deleteLeague.mockRejectedValue(new ApiError(409, "Switch to another franchise first."));
    render(<LeaguesHub initialFranchises={[active, other]} />);
    const card = screen.getByRole("listitem", { name: "Krakens Dynasty" });
    await userEvent.click(within(card).getByRole("button", { name: "Delete Harbor Coast League" }));
    await userEvent.click(within(card).getByRole("button", { name: "Delete league" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Switch to another franchise");
  });
});

describe("TeamEditDialog", () => {
  it("saves identity changes and refreshes", async () => {
    mocked.updateTeam.mockResolvedValue(teamDetail);
    const onClose = vi.fn();
    render(<TeamEditDialog team={teamDetail} onClose={onClose} />);

    const nickname = screen.getByRole("textbox", { name: "Nickname" });
    await userEvent.clear(nickname);
    await userEvent.type(nickname, "Ironsides");
    expect(screen.getByText("Ironsides")).toBeInTheDocument(); // live crest preview
    await userEvent.click(screen.getByRole("button", { name: "Save team" }));

    expect(mocked.updateTeam).toHaveBeenCalledWith(1, expect.objectContaining({ nickname: "Ironsides", abbreviation: "HFD" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(router.refresh).toHaveBeenCalled();
  });

  it("shows a conflict error and stays open", async () => {
    mocked.updateTeam.mockRejectedValue(new ApiError(409, "ALB is already used by the Albany Sentinels"));
    const onClose = vi.fn();
    render(<TeamEditDialog team={teamDetail} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Save team" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already used");
    expect(onClose).not.toHaveBeenCalled();
  });
});
