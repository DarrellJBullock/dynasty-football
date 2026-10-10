import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import type { ImportPreview, ImportRow } from "@/lib/types";
import { teamDetail } from "@/test/fixtures";
import { ImportDialog } from "./ImportDialog";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { previewImport: vi.fn(), commitImport: vi.fn() } };
});

const mocked = vi.mocked(api);

function row(overrides: Partial<ImportRow>): ImportRow {
  return {
    row_number: 1, status: "ok", first_name: "Trey", last_name: "Calloway", position: "RB",
    jersey_number: 22, age: 24, height_in: 71, weight_lb: 205, college: "Undrafted",
    overall: 81, potential: 81, salary: 10_800_000, messages: [], ...overrides,
  };
}

function preview(overrides: Partial<ImportPreview> = {}): ImportPreview {
  const rows = overrides.rows ?? [
    row({}),
    row({ row_number: 2, status: "warning", first_name: "Miles", last_name: "Ingram",
          messages: [{ level: "warning", message: "speed 105 capped at 99." }] }),
    row({ row_number: 3, status: "error", first_name: "Quinn", last_name: "Abernathy",
          position: null, overall: null, salary: null,
          messages: [{ level: "error", message: "Unknown position 'LS'." }] }),
  ];
  return {
    format: "csv", mode: "append", file_warnings: ["Ignored unrecognized column(s): Notes."],
    rows, summary: { total: 3, valid: 2, warnings: 1, errors: 1 }, roster_before: 51,
    released: 0, roster_after: 53, roster_max: 53, payroll_after: 240_000_000,
    salary_cap: 255_000_000, can_commit: false, ...overrides,
  };
}

const file = new File(["first_name,last_name,position\n"], "my-team.csv", { type: "text/csv" });

function renderDialog(onImported = vi.fn()) {
  render(<ImportDialog teamId={1} rosterCount={51} onImported={onImported} onClose={vi.fn()} />);
  return onImported;
}

async function upload() {
  await userEvent.upload(screen.getByLabelText("Roster file"), file);
}

beforeEach(() => vi.clearAllMocks());

describe("ImportDialog", () => {
  it("previews an uploaded file and summarizes it", async () => {
    mocked.previewImport.mockResolvedValue(preview());
    renderDialog();
    await upload();

    expect(mocked.previewImport).toHaveBeenCalledWith(1, file, "append");
    const region = await screen.findByRole("region", { name: "Import preview" });
    expect(within(region).getByText("Ignored unrecognized column(s): Notes.")).toBeInTheDocument();
    expect(within(region).getByText("Unknown position 'LS'.")).toBeInTheDocument();
    expect(within(region).getByText(/Roster 51/)).toHaveTextContent("Roster 51 → 53/53");
    expect(screen.getAllByTestId("import-row")).toHaveLength(3);
  });

  it("blocks import while rows have errors unless they are skipped", async () => {
    mocked.previewImport.mockResolvedValue(preview());
    mocked.commitImport.mockResolvedValue({ imported: 2, released: 0, skipped: 1, team: teamDetail });
    const onImported = renderDialog();
    await upload();

    const importButton = await screen.findByRole("button", { name: "Import 2 players" });
    expect(importButton).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Skip 1 row with errors" }));
    expect(importButton).toBeEnabled();
    await userEvent.click(importButton);

    expect(mocked.commitImport).toHaveBeenCalledWith(1, file, "append", true);
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(
      expect.objectContaining({ imported: 2, skipped: 1 })));
  });

  it("re-previews when switching to replace mode", async () => {
    mocked.previewImport.mockResolvedValueOnce(preview());
    mocked.previewImport.mockResolvedValueOnce(
      preview({ mode: "replace", released: 51, roster_after: 2 }));
    renderDialog();
    await upload();
    await screen.findByRole("region", { name: "Import preview" });

    await userEvent.click(screen.getByRole("radio", { name: /Replace roster/ }));
    expect(mocked.previewImport).toHaveBeenLastCalledWith(1, file, "replace");
    expect(await screen.findByText(/51 released to free agency/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace roster with 2 players" })).toBeInTheDocument();
  });

  it("filters to rows with issues", async () => {
    mocked.previewImport.mockResolvedValue(preview());
    renderDialog();
    await upload();
    await screen.findByRole("region", { name: "Import preview" });

    await userEvent.click(screen.getByRole("checkbox", { name: "Only rows with issues" }));
    const statuses = screen.getAllByTestId("import-row").map((r) => r.dataset.status);
    expect(statuses).toEqual(["warning", "error"]);
  });

  it("shows file-level errors from the server", async () => {
    mocked.previewImport.mockRejectedValue(new ApiError(422, "Invalid JSON: Expecting value"));
    renderDialog();
    await upload();
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid JSON");
    expect(screen.queryByRole("region", { name: "Import preview" })).not.toBeInTheDocument();
  });

  it("shows commit errors and lets the user retry", async () => {
    mocked.previewImport.mockResolvedValue(
      preview({ rows: [row({})], summary: { total: 1, valid: 1, warnings: 0, errors: 0 }, can_commit: true }));
    mocked.commitImport.mockRejectedValue(new ApiError(422, "No valid rows to import."));
    renderDialog();
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Import 1 player" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No valid rows");
    expect(screen.getByRole("button", { name: "Import 1 player" })).toBeEnabled();
  });

  it("links to downloadable templates", () => {
    renderDialog();
    expect(screen.getByRole("link", { name: "Excel" })).toHaveAttribute(
      "href", "http://localhost:8000/api/roster-import/template.xlsx");
  });
});
