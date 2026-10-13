import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LockerRoom, PlayerMood } from "@/lib/types";
import { team } from "@/test/fixtures";
import { LockerRoomPanel } from "./LockerRoomPanel";
import { PlayerMoodPanel } from "./PlayerMoodPanel";

const mood: PlayerMood = {
  player_id: 7, name: "Ari Vance", position: "WR", overall: 81, drive: "mercenary",
  drive_label: "Mercenary", drive_means: "wants to be paid", temperament: "volatile",
  temperament_label: "Volatile", temperament_means: "feels everything more", base: 60,
  parts: [["Wants to start", -15], ["Underpaid", -18]], mood: 27, label: "Miserable", role: "benched",
};

describe("PlayerMoodPanel", () => {
  it("shows the traits and what moved the mood", () => {
    render(<PlayerMoodPanel mood={mood} />);
    const panel = screen.getByRole("region", { name: "Personality and mood" });
    expect(panel).toHaveTextContent("MercenaryDrive: wants to be paid.");
    expect(panel).toHaveTextContent("VolatileTemperament: feels everything more.");
    expect(screen.getByRole("meter", { name: "Mood" })).toHaveAttribute("aria-valuenow", "27");
    const moved = within(panel).getByRole("list", { name: "What moved his mood" });
    expect(within(moved).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Coming into the season60", "Wants to start-15", "Underpaid-18"]);
  });
});

describe("LockerRoomPanel", () => {
  it("shows the team's mood and the least happy", () => {
    const room: LockerRoom = { team, average: 58, counts: { Happy: 10, Content: 30, Unhappy: 10, Miserable: 3 },
      unhappiest: [{ player_id: 7, name: "Ari Vance", position: "WR", overall: 81, mood: 27,
        label: "Miserable", reason: "Underpaid" }] };
    render(<LockerRoomPanel room={room} />);
    const panel = screen.getByRole("region", { name: "Locker room" });
    expect(panel).toHaveTextContent("10 happy · 30 content · 10 unhappy · 3 miserable");
    expect(screen.getByRole("meter", { name: "Average mood" })).toHaveAttribute("aria-valuenow", "58");
    const least = within(panel).getByRole("list", { name: "Least happy" });
    expect(least).toHaveTextContent("WRAri VanceUnderpaidMiserable · 27");
    expect(within(least).getByRole("link", { name: "Ari Vance" })).toHaveAttribute("href", "/players/7");
  });
});
