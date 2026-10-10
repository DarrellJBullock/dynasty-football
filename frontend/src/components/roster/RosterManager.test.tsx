import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { makePlayer, makePlayerDetail, teamDetail } from "@/test/fixtures";
import { RosterManager } from "./RosterManager";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      team: vi.fn(),
      player: vi.fn(),
      updatePlayer: vi.fn(),
      releasePlayer: vi.fn(),
      freeAgents: vi.fn(),
      signPlayer: vi.fn(),
      createPlayer: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

const qb = makePlayer({ first_name: "Keegan", last_name: "Quarles", position: "QB", overall: 82, jersey_number: 15 });
const wr = makePlayer({ first_name: "Garrett", last_name: "Draper", position: "WR", position_group: "WR", overall: 81, jersey_number: 88 });
const cb = makePlayer({ first_name: "Terrell", last_name: "Stroud", position: "CB", position_group: "DB", overall: 86, jersey_number: 24 });

function renderManager(roster = [qb, wr, cb], team = { ...teamDetail, roster_count: 3 }) {
  return render(
    <RosterManager initialTeam={team} initialRoster={roster} leagueId={1} seasonYear={2026} />,
  );
}

function rowNames() {
  const table = screen.getByRole("table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[1].querySelector("button")?.textContent);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.team.mockResolvedValue(teamDetail);
});

describe("RosterManager", () => {
  it("lists the roster sorted by overall", () => {
    renderManager();
    expect(rowNames()).toEqual(["Terrell Stroud", "Keegan Quarles", "Garrett Draper"]);
  });

  it("filters by position group tab", async () => {
    renderManager();
    await userEvent.click(screen.getByRole("tab", { name: /^WR/ }));
    expect(rowNames()).toEqual(["Garrett Draper"]);
    await userEvent.click(screen.getByRole("tab", { name: /^LB/ }));
    expect(screen.getByText("No players match these filters.")).toBeInTheDocument();
  });

  it("searches by name", async () => {
    renderManager();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search roster" }), "quar");
    expect(rowNames()).toEqual(["Keegan Quarles"]);
  });

  it("re-sorts when a column header is clicked", async () => {
    renderManager();
    await userEvent.click(screen.getByRole("button", { name: "Player" }));
    expect(rowNames()).toEqual(["Garrett Draper", "Keegan Quarles", "Terrell Stroud"]);
  });

  it("opens the player card and releases the player", async () => {
    mocked.player.mockResolvedValue(makePlayerDetail({ ...qb }));
    mocked.releasePlayer.mockResolvedValue({ ...makePlayerDetail({ ...qb }), team_id: null, contract: null });
    renderManager();

    await userEvent.click(screen.getByRole("button", { name: "Keegan Quarles" }));
    const panel = await screen.findByRole("dialog", { name: "Player details" });
    expect(await within(panel).findByText("Quarles")).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole("button", { name: "Release" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm release" }));

    expect(mocked.releasePlayer).toHaveBeenCalledWith(qb.id);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(rowNames()).not.toContain("Keegan Quarles");
    expect(screen.getByRole("status")).toHaveTextContent("Keegan Quarles was released");
    expect(mocked.team).toHaveBeenCalled();
  });

  it("edits ratings and sends only the changed fields", async () => {
    const detail = makePlayerDetail({ ...qb });
    mocked.player.mockResolvedValue(detail);
    mocked.updatePlayer.mockImplementation(async (_id, update) => ({
      ...detail,
      ...update,
      overall: 90,
      ratings: { ...detail.ratings, ...update.ratings },
    }) as typeof detail);
    renderManager();

    await userEvent.click(screen.getByRole("button", { name: "Keegan Quarles" }));
    const panel = await screen.findByRole("dialog", { name: "Player details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Edit player" }));

    const jersey = within(panel).getByRole("spinbutton", { name: "Jersey #" });
    await userEvent.clear(jersey);
    await userEvent.type(jersey, "7");
    await userEvent.click(within(panel).getByRole("button", { name: "Save changes" }));

    expect(mocked.updatePlayer).toHaveBeenCalledWith(qb.id, { jersey_number: 7 });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved Keegan Quarles"));
  });

  it("shows API errors from a failed save", async () => {
    mocked.player.mockResolvedValue(makePlayerDetail({ ...qb }));
    mocked.updatePlayer.mockRejectedValue(new Error("jersey #88 is already worn by Garrett Draper"));
    renderManager();

    await userEvent.click(screen.getByRole("button", { name: "Keegan Quarles" }));
    const panel = await screen.findByRole("dialog", { name: "Player details" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Edit player" }));
    const jersey = within(panel).getByRole("spinbutton", { name: "Jersey #" });
    await userEvent.clear(jersey);
    await userEvent.type(jersey, "88");
    await userEvent.click(within(panel).getByRole("button", { name: "Save changes" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("already worn");
  });

  it("disables creating players when the roster is full", () => {
    renderManager([qb, wr, cb], { ...teamDetail, roster_max: 3 });
    expect(screen.getByRole("button", { name: "+ Create player" })).toBeDisabled();
  });

  it("moves focus into dialogs, closes on Escape, and restores focus", async () => {
    mocked.freeAgents.mockResolvedValue([]);
    renderManager();
    const trigger = screen.getByRole("button", { name: "Free agents" });

    await userEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Free agents" });
    expect(dialog).toHaveFocus();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("keeps Tab focus inside the player panel", async () => {
    mocked.player.mockResolvedValue(makePlayerDetail({ ...qb }));
    renderManager();

    await userEvent.click(screen.getByRole("button", { name: "Keegan Quarles" }));
    const panel = await screen.findByRole("dialog", { name: "Player details" });
    await within(panel).findByRole("button", { name: "Edit player" });

    for (let i = 0; i < 6; i++) {
      await userEvent.tab();
      expect(panel).toContainElement(document.activeElement as HTMLElement);
    }
    await userEvent.tab({ shift: true });
    expect(panel).toContainElement(document.activeElement as HTMLElement);
  });

  it("signs a free agent", async () => {
    const fa = makePlayer({ first_name: "Jamal", last_name: "Nash", position: "QB", team_id: null, contract: null });
    mocked.freeAgents.mockResolvedValue([fa]);
    mocked.signPlayer.mockResolvedValue({ ...makePlayerDetail({ ...fa }), team_id: 1 });
    renderManager();

    await userEvent.click(screen.getByRole("button", { name: "Free agents" }));
    const dialog = await screen.findByRole("dialog", { name: "Free agents" });
    await userEvent.click(await within(dialog).findByRole("button", { name: "Sign Jamal Nash" }));

    expect(mocked.signPlayer).toHaveBeenCalledWith(teamDetail.id, fa.id);
    await waitFor(() => expect(rowNames()).toContain("Jamal Nash"));
    expect(screen.getByTestId("roster-count")).toHaveTextContent("4");
  });
});
