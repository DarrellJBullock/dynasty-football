import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { Turn, TurnMember } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { SimControls } from "./SimControls";
import { TurnPanel } from "./TurnPanel";

const router = { push: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { turn: vi.fn(), setReady: vi.fn(), advanceLeague: vi.fn() } };
});
const mocked = vi.mocked(api);

const me: TurnMember = { member_id: 1, display_name: "Sam", team, ready: false, is_you: true };
const robin: TurnMember = { member_id: 2, display_name: "Robin", team: opponent, ready: true, is_you: false };
const turn: Turn = { step: "Week 3", step_key: "1:week:3", managers: [me, robin], all_ready: false,
  can_advance: true, draft_clock_minutes: 1440, advance_minute_utc: null, next_advance_at: null,
  pick_clock_ends_at: null };

beforeEach(() => vi.clearAllMocks());

describe("TurnPanel", () => {
  it("shows what's next and who's ready, and checks you in", async () => {
    mocked.turn.mockResolvedValue(turn);
    mocked.setReady.mockResolvedValue({ ...turn, all_ready: true, managers: [{ ...me, ready: true }, robin] });
    render(<TurnPanel leagueId={1} />);
    const panel = await screen.findByRole("region", { name: "This step" });
    expect(within(panel).getByRole("heading", { name: "Next: Week 3" })).toBeInTheDocument();
    expect(panel).toHaveTextContent("1 of 2 ready");
    expect(within(panel).getByRole("list", { name: "Managers" })).toHaveTextContent("Robin: ready");
    await userEvent.click(within(panel).getByRole("button", { name: "I'm ready" }));
    expect(mocked.setReady).toHaveBeenCalledWith(1, true);
    expect(await within(panel).findByText("Everyone's ready")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Ready ✓" })).toHaveAttribute("aria-pressed", "true");
  });

  it("lets a commissioner advance, ready or not, and refreshes the page", async () => {
    mocked.turn.mockResolvedValue(turn);
    mocked.advanceLeague.mockResolvedValue({ ...turn, step: "Week 4" });
    render(<TurnPanel leagueId={1} />);
    await userEvent.click(await screen.findByRole("button", { name: "Advance: Week 3" }));
    expect(mocked.advanceLeague).toHaveBeenCalledWith(1);
    expect(await screen.findByRole("heading", { name: "Next: Week 4" })).toBeInTheDocument();
    expect(router.refresh).toHaveBeenCalled();
  });

  it("gives a manager no advance button, and shows why a step failed", async () => {
    mocked.turn.mockResolvedValue({ ...turn, can_advance: false,
      next_advance_at: "2026-10-13T01:00:00Z" });
    mocked.setReady.mockRejectedValue(new ApiError(409, "A simulation is running in this league."));
    render(<TurnPanel leagueId={1} />);
    const panel = await screen.findByRole("region", { name: "This step" });
    expect(panel).toHaveTextContent("· advances");
    expect(within(panel).queryByRole("button", { name: /Advance/ })).toBeNull();
    await userEvent.click(within(panel).getByRole("button", { name: "I'm ready" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent("A simulation is running");
  });

  it("isn't there in a league played alone", async () => {
    mocked.turn.mockResolvedValue({ ...turn, managers: [me] });
    const { container } = render(<TurnPanel leagueId={1} />);
    await vi.waitFor(() => expect(mocked.turn).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("SimControls for a manager", () => {
  it("says the commissioner advances the season, with no buttons", () => {
    const season = { id: 5, league_id: 1, year: 2026, phase: "regular_season", current_week: 3, weeks: 17,
      regular_season_complete: false, next_round: null, champion: null };
    render(<SimControls season={season} teamId={team.id} canRun={false} />);
    expect(screen.getByRole("status")).toHaveTextContent("The commissioner advances the season.");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
