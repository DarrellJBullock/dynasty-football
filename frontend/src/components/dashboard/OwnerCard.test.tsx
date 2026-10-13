import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Owner } from "@/lib/types";
import { team } from "@/test/fixtures";
import { OwnerCard } from "./OwnerCard";

const owner: Owner = {
  team, name: "Morgan Hale", priority: "win_now", wants: "wants to win now", patience: 2,
  confidence: 64, hot_seat: false, market: "large", fan_mood: 58,
  fan_parts: [["Record", 6], ["2 star players", 2]], season_year: 2027, situation: "contender",
  goals: [
    { label: "Win the championship", kind: "title", status: "behind", primary: true },
    { label: "Win 11 games", kind: "wins", status: "on_track", primary: false },
    { label: "Make the playoffs", kind: "playoffs", status: "met", primary: false },
  ],
  last_review: {
    year: 2026, verdict: "is pleased", results: [{ label: "Make the playoffs", met: true }],
    confidence_before: 60, confidence_after: 64,
    confidence_parts: [["Make the playoffs", 10], ["Win the championship", -10], ["Fan mood", 4]],
    fan_mood_before: 45, fan_mood_after: 70, fan_parts: [["Record", 12], ["Made the playoffs", 5]],
  },
};

describe("OwnerCard", () => {
  it("shows what the owner wants, the goals, and the two meters", () => {
    render(<OwnerCard owner={owner} />);
    const card = screen.getByRole("region", { name: "The owner" });
    expect(card).toHaveTextContent("Morgan Hale wants to win now");
    expect(card).toHaveTextContent("patience 2 of 5 · large market");
    expect(card).toHaveTextContent("Set with the roster a contender.");
    const goals = within(card).getByRole("list", { name: "Goals" });
    expect(within(goals).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Win the championship · main goalBehind", "Win 11 gamesOn track", "Make the playoffsMet"]);
    expect(screen.getByRole("meter", { name: "Owner confidence" })).toHaveAttribute("aria-valuenow", "64");
    expect(screen.getByRole("meter", { name: "Fan mood" })).toHaveAttribute("aria-valuenow", "58");
    expect(within(card).getByRole("list", { name: "What moved the fans this season" }))
      .toHaveTextContent("Record+6");
    expect(within(card).queryByRole("status")).not.toBeInTheDocument();
  });

  it("opens last season's review, part by part", async () => {
    render(<OwnerCard owner={owner} />);
    await userEvent.click(screen.getByText(/2026 review: the owner is pleased/));
    expect(screen.getByText(/confidence 60 → 64/)).toBeInTheDocument();
    const moved = screen.getByRole("list", { name: "What moved the owner" });
    expect(moved).toHaveTextContent("Win the championship-10");
    expect(screen.getByText("Fan mood 45 → 70")).toBeInTheDocument();
  });

  it("warns when the seat is hot, and waits for the preseason's goals", () => {
    render(<OwnerCard owner={{ ...owner, hot_seat: true, confidence: 22, goals: [], situation: null,
      last_review: null }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Hot seat: the owner is losing patience");
    expect(screen.getByText(/sets the season's goals when the preseason opens/)).toBeInTheDocument();
    expect(screen.queryByText(/review/)).not.toBeInTheDocument();
  });
});
