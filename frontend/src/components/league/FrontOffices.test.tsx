import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { FrontOffice } from "@/lib/types";
import { opponent, team } from "@/test/fixtures";
import { FrontOffices } from "./FrontOffices";

const offices: FrontOffice[] = [
  { team: opponent, direction: "rebuild", label: "Rebuilding",
    reasons: ["28th of 32 by team rating", "Starters average 27.9 years old"], manager: null },
  { team, direction: null, label: null, reasons: [], manager: "Sam" },
];

describe("FrontOffices", () => {
  it("lists members' teams first, then each AI team's direction and why", async () => {
    render(<FrontOffices offices={offices} />);
    const panel = screen.getByRole("region", { name: "Front offices" });
    const items = within(panel).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(`${team.full_name}Run by Sam`);
    expect(items[1]).toHaveTextContent(`${opponent.full_name}Rebuilding`);
    expect(screen.getByText("28th of 32 by team rating")).not.toBeVisible();
    await userEvent.click(screen.getByText("Rebuilding"));
    expect(screen.getByText("28th of 32 by team rating")).toBeVisible();
  });
});
