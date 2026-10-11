import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FieldPreviewLoader } from "./FieldPreviewLoader";

// WebGL isn't available in jsdom: stand in for the scene and report its camera.
vi.mock("next/dynamic", () => ({
  default: () => function Scene({ camera }: { camera: string }) {
    return <div data-testid="scene" data-camera={camera} />;
  },
}));

describe("FieldPreviewLoader", () => {
  it("switches camera presets", async () => {
    render(<FieldPreviewLoader homeColor="#000" homeAccent="#fff" awayColor="#f00"
      nickname="Ironclads" abbreviation="HFD" />);
    expect(screen.getByTestId("scene")).toHaveAttribute("data-camera", "overview");
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "All-22" }));
    expect(screen.getByTestId("scene")).toHaveAttribute("data-camera", "all22");
    expect(screen.getByRole("button", { name: "All-22" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Overview" })).toHaveAttribute("aria-pressed", "false");
  });
});
