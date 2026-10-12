import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExportMenu } from "./ExportMenu";

describe("ExportMenu", () => {
  it("offers CSV, Excel, and JSON downloads for the team", async () => {
    render(<ExportMenu teamId={97} />);
    const button = screen.getByRole("button", { name: "Export" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(button);
    const items = screen.getAllByRole("menuitem");
    expect(items.map((a) => a.getAttribute("href"))).toEqual([
      "/api/teams/97/roster-export.csv",
      "/api/teams/97/roster-export.xlsx",
      "/api/teams/97/roster-export.json",
    ]);
    expect(items.every((a) => a.hasAttribute("download"))).toBe(true);
  });

  it("closes on Escape and on outside click", async () => {
    render(
      <div>
        <ExportMenu teamId={1} />
        <p>outside</p>
      </div>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByText("outside"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
