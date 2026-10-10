import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { dashboard } from "@/test/fixtures";
import { DashboardView } from "./DashboardView";

// WebGL isn't available in jsdom; the 3D preview is exercised in the browser.
vi.mock("@/components/field/FieldPreviewLoader", () => ({
  FieldPreviewLoader: () => <div data-testid="field-preview" />,
}));

describe("DashboardView", () => {
  it("shows the franchise identity and team rating", () => {
    render(<DashboardView data={dashboard} />);
    expect(screen.getByRole("heading", { level: 1, name: "Ironclads" })).toBeInTheDocument();
    expect(screen.getByText(/Ironclads Dynasty · 2026 Preseason/)).toBeInTheDocument();
    expect(screen.getByTitle(/79 overall/)).toBeInTheDocument();
    expect(screen.getByTestId("field-preview")).toBeInTheDocument();
  });

  it("shows the next opponent with home/away", () => {
    render(<DashboardView data={dashboard} />);
    const card = screen.getByRole("region", { name: "Next game" });
    expect(within(card).getByText("Albuquerque Roadrunners")).toBeInTheDocument();
    expect(within(card).getByText("Week 1 · Home")).toBeInTheDocument();
  });

  it("shows cap space and roster count", () => {
    render(<DashboardView data={dashboard} />);
    expect(within(screen.getByRole("region", { name: "Salary cap" })).getByText("$15.3M")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Active roster" })).getByText("53")).toBeInTheDocument();
  });

  it("lists top players, standings, alerts and schedule", () => {
    render(<DashboardView data={dashboard} />);
    expect(screen.getByText("Terrell Stroud")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "ATL North standings" })).toHaveTextContent("Hartford Ironclads");
    expect(screen.getByText("21 contract(s) expire after this season.")).toBeInTheDocument();
    const schedule = screen.getByRole("region", { name: "Upcoming schedule" });
    expect(within(schedule).getByText("vs Roadrunners")).toBeInTheDocument();
    expect(within(schedule).getByText("@ Roadrunners")).toBeInTheDocument();
  });
});
