import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { Coaches, StaffMember, TeamStaff } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { careerLine, StaffView } from "./StaffView";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { hireStaff: vi.fn(), fireStaff: vi.fn(), extendStaff: vi.fn(), staffMarket: vi.fn() } };
});
const mocked = vi.mocked(api);

const none = { seasons: 0, wins: 0, losses: 0, ties: 0, playoff_wins: 0, titles: 0, coach_of_the_year: 0 };

function member(id: number, overrides: Partial<StaffMember> = {}): StaffMember {
  return { id, role: "head_coach", role_label: "Head coach", duty: "Runs the team.", name: `Coach ${id}`,
    age: 52, rating: 88, specialty: "offense", effect: "Every young player grows 8% faster.", salary: 9_100_000, contract_end: 2028, team, career: none,
    ...overrides };
}

const staff: TeamStaff = { team, payroll: 15_000_000, members: [
  member(1),
  member(2, { role: "offensive_coordinator", role_label: "Offensive coordinator", specialty: "QB", rating: 61,
    contract_end: 2026, duty: "Develops the offense's young players." }),
  member(3, { role: "trainer", role_label: "Head trainer", specialty: null, rating: 47, contract_end: 2025 }),
] };
const coaches: Coaches = {
  head_coaches: [member(1, { career: { ...none, seasons: 3, wins: 33, losses: 18, titles: 1 } }),
    member(9, { team: opponent, name: "Rival Coach" })],
  coach_of_the_year: [{ year: 2027, staff_id: 1, name: "Coach 1", team, wins: 13, losses: 4, ties: 0 }],
};

beforeEach(() => vi.clearAllMocks());

describe("StaffView", () => {
  it("shows each staff member's rating, contract and what they do", () => {
    render(<StaffView staff={staff} coaches={coaches} teams={[team, opponent]} season={2026} />);
    const head = screen.getByRole("article", { name: "Head coach" });
    expect(head).toHaveTextContent("Coach 1");
    expect(head).toHaveTextContent("offense specialist");
    expect(head).toHaveTextContent("Every young player grows 8% faster.");
    expect(head).toHaveTextContent("3 seasons, through 2028");
    expect(head).toHaveTextContent("First season");
    expect(screen.getByRole("article", { name: "Offensive coordinator" })).toHaveTextContent("ends after 2026");
    expect(screen.getByRole("article", { name: "Head trainer" })).toHaveTextContent("expired");
    expect(screen.getByText(/Staff payroll \$15/)).toBeInTheDocument();
  });

  it("lists the league's head coaches and Coach of the Year, and switches teams", async () => {
    render(<StaffView staff={staff} coaches={coaches} teams={[team, opponent]} season={2026} />);
    const table = screen.getByRole("table", { name: "Head coaches" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("33-18 · 1 title");
    expect(screen.getByRole("list", { name: "Coach of the Year by season" })).toHaveTextContent(/2027.*Coach 1\s*13-4/);
    await userEvent.selectOptions(screen.getByLabelText("Team"), String(opponent.id));
    expect(router.push).toHaveBeenCalledWith(`/staff?team=${opponent.id}`);
  });

  it("sums up a career in a line", () => {
    expect(careerLine({ ...none, seasons: 1, wins: 9, losses: 8, playoff_wins: 1 })).toBe("1 season · 9-8 · 1 playoff win");
    expect(careerLine({ ...none, seasons: 12, wins: 120, losses: 80, ties: 2, titles: 2, coach_of_the_year: 3 }))
      .toBe("12 seasons · 120-80-2 · 2 titles · 3× Coach of the Year");
  });
});

describe("StaffView for the team you run", () => {
  const budget = { year: 2026, budget: 20_000_000, payroll: 15_000_000, dead_money: 1_200_000, room: 5_000_000 };
  const open: TeamStaff = { ...staff, members: staff.members.filter((m) => m.role !== "trainer"),
    vacancies: ["trainer"], budget };
  const candidate = member(7, { role: "trainer", role_label: "Head trainer", name: "Dana Pike", team: null,
    rating: 74, salary: 880_000, specialty: null });
  const market = { year: 2026, budget, candidates: [candidate,
    member(8, { role: "scout", role_label: "Scout", name: "Ari Moss", team: null, salary: 700_000 })] };

  it("shows the budget, an open job, and hires into it from the market", async () => {
    mocked.hireStaff.mockResolvedValue({ ...staff, vacancies: [], budget: { ...budget, room: 4_120_000 } });
    mocked.staffMarket.mockResolvedValue({ ...market, candidates: market.candidates.slice(1) });
    render(<StaffView staff={open} coaches={coaches} teams={[team]} season={2026} market={market} leagueId={4} />);
    expect(screen.getByText(/including \$1.2M owed to staff let go/)).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Head trainer (open)" })).toHaveTextContent("Hire from the market below.");
    const table = screen.getByRole("table", { name: "Staff on the market" });
    expect(within(table).getByRole("button", { name: "Hire Ari Moss" })).toBeDisabled(); // (no open scout job)
    await userEvent.selectOptions(screen.getByLabelText("Contracts of"), "2");
    await userEvent.click(within(table).getByRole("button", { name: "Hire Dana Pike" }));
    expect(mocked.hireStaff).toHaveBeenCalledWith(team.id, 7, 2);
    expect(await screen.findByRole("status")).toHaveTextContent("Dana Pike is your new head trainer.");
    expect(mocked.staffMarket).toHaveBeenCalledWith(4);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("extends a contract in its final season, lets someone go, and shows refusals", async () => {
    mocked.extendStaff.mockResolvedValue(staff);
    mocked.staffMarket.mockResolvedValue(market);
    mocked.fireStaff.mockRejectedValueOnce(new ApiError(409, "They aren't on a team."));
    render(<StaffView staff={staff} coaches={coaches} teams={[team]} season={2026} market={market} leagueId={4} />);
    const oc = screen.getByRole("article", { name: "Offensive coordinator" });
    expect(within(screen.getByRole("article", { name: "Head coach" })).queryByRole("button", { name: /Extend/ })).toBeNull();
    await userEvent.click(within(oc).getByRole("button", { name: "Extend 3 seasons" }));
    expect(mocked.extendStaff).toHaveBeenCalledWith(2, 3);
    await userEvent.click(within(oc).getByRole("button", { name: "Let go" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("They aren't on a team.");
  });

  it("offers no moves on another team's page", () => {
    render(<StaffView staff={staff} coaches={coaches} teams={[team]} season={2026} />);
    expect(screen.queryByRole("button", { name: "Let go" })).toBeNull();
    expect(screen.queryByRole("region", { name: "The market" })).toBeNull();
  });
});
