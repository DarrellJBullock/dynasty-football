import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Coaches, StaffMember, TeamStaff } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { careerLine, StaffView } from "./StaffView";

const router = { push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const none = { seasons: 0, wins: 0, losses: 0, ties: 0, playoff_wins: 0, titles: 0, coach_of_the_year: 0 };

function member(id: number, overrides: Partial<StaffMember> = {}): StaffMember {
  return { id, role: "head_coach", role_label: "Head coach", duty: "Runs the team.", name: `Coach ${id}`,
    age: 52, rating: 88, specialty: "offense", salary: 9_100_000, contract_end: 2028, team, career: none,
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
