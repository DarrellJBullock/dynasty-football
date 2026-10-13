import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import type { GmCareer } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { CareerView } from "./CareerView";

vi.mock("@/lib/navigation", () => ({ hardNavigate: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { takeJob: vi.fn() } };
});
const mocked = vi.mocked(api);

const career: GmCareer = {
  name: "Sam", team, fired: false,
  stints: [{ team, from_year: 2026, to_year: null, seasons: 2, wins: 20, losses: 14, ties: 0,
    playoffs: 1, titles: 0, ended: null }],
  wins: 20, losses: 14, ties: 0, playoffs: 1, titles: 0, firings: 0, open_jobs: [], firing: "auto",
};

const fired: GmCareer = {
  ...career, fired: true, firings: 1,
  stints: [{ ...career.stints[0], to_year: 2027, ended: "fired" }],
  open_jobs: [{ team: opponent, why: "The owner just fired the general manager.", owner: "Morgan Hale",
    wants: "wants to win now", patience: 2, market: "large", fan_mood: 40, rating: 71,
    situation: "rebuilding", last_season: "4-13" }],
};

beforeEach(() => vi.clearAllMocks());

describe("CareerView", () => {
  it("shows every team you've run and the totals", () => {
    render(<CareerView initial={career} />);
    expect(screen.getByRole("region", { name: "Record" })).toHaveTextContent("20-14");
    expect(screen.getByRole("region", { name: "Times fired" })).toHaveTextContent("0");
    const row = screen.getByRole("row", { name: new RegExp(team.full_name) });
    expect(row).toHaveTextContent("2026–now (2)");
    expect(row).toHaveTextContent("Still there");
    expect(screen.queryByRole("region", { name: "Open jobs" })).not.toBeInTheDocument();
  });

  it("fired: takes another job, with a confirm, and starts afresh", async () => {
    mocked.takeJob.mockResolvedValue({ ...career, team: opponent });
    render(<CareerView initial={fired} />);
    const jobs = screen.getByRole("region", { name: "Open jobs" });
    expect(jobs).toHaveTextContent(`You've been fired by the ${team.full_name}`);
    expect(jobs).toHaveTextContent("Morgan Hale wants to win now (patience 2 of 5)");
    expect(jobs).toHaveTextContent("71 overall · Rebuilding");
    await userEvent.click(within(jobs).getByRole("button", { name: `Take the ${opponent.full_name} job` }));
    await userEvent.click(within(jobs).getByRole("button", { name: "Confirm: take this job" }));
    expect(mocked.takeJob).toHaveBeenCalledWith(opponent.id);
    await waitFor(() => expect(hardNavigate).toHaveBeenCalledWith("/"));
    expect(screen.getByRole("row", { name: new RegExp(team.full_name) })).toHaveTextContent("Fired");
  });

  it("shows why a job couldn't be taken", async () => {
    mocked.takeJob.mockRejectedValue(new Error("That team isn't looking for a general manager."));
    render(<CareerView initial={fired} />);
    await userEvent.click(screen.getByRole("button", { name: `Take the ${opponent.full_name} job` }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm: take this job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't looking");
    expect(hardNavigate).not.toHaveBeenCalled();
  });
});
