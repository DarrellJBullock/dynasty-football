import { expect, test } from "./support/fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/roster");
  await expect(page.getByTestId("roster-count")).toHaveText("53");
});

test("exports the roster and re-imports it unchanged", async ({ page }, testInfo) => {
  const names = page.getByRole("table").locator("tbody tr td:nth-child(2) button");
  await expect(names).toHaveCount(53);
  const namesBefore = await names.allTextContents();

  await page.getByRole("button", { name: "Export" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("menuitem", { name: /CSV/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("HFD-roster-2026.csv");
  const file = testInfo.outputPath("roster.csv");
  await download.saveAs(file);

  await page.getByRole("button", { name: "Import" }).click();
  const dialog = page.getByRole("dialog", { name: "Import roster" });
  await dialog.getByLabel("Roster file").setInputFiles(file);
  await dialog.getByRole("radio", { name: /Replace roster/ }).check();
  const preview = dialog.getByRole("region", { name: "Import preview" });
  await expect(preview).toContainText("Roster 53 → 53/53");
  await expect(preview).toContainText("53 released to free agency");
  await dialog.getByRole("button", { name: "Replace roster with 53 players" }).click();

  await expect(page.getByRole("status")).toHaveText("Imported 53 players, released 53 to free agency.");
  await expect(names).toHaveCount(53);
  const namesAfter = await names.allTextContents();
  expect(namesAfter.sort()).toEqual(namesBefore.sort());
});

test("previews a messy file with row errors and imports the valid rows", async ({ page }) => {
  const csv = [
    "Name,Pos,#,Ht,OVR,SPD",
    "Trey Calloway,HB,22,5-11,81,94",
    "Quinn Abernathy,LS,48,6-2,60,",
  ].join("\n");

  await page.getByRole("button", { name: "Import" }).click();
  const dialog = page.getByRole("dialog", { name: "Import roster" });
  await dialog.getByLabel("Roster file").setInputFiles({
    name: "messy.csv", mimeType: "text/csv", buffer: Buffer.from(csv),
  });
  await dialog.getByRole("radio", { name: /Replace roster/ }).check();
  await expect(dialog.getByText("Unknown position 'LS'.")).toBeVisible();
  const calloway = dialog.getByTestId("import-row").filter({ hasText: "Trey Calloway" });
  await expect(calloway.getByTitle("81 overall (great)")).toBeVisible();

  const importButton = dialog.getByRole("button", { name: "Replace roster with 1 player" });
  await expect(importButton).toBeDisabled();
  await dialog.getByRole("checkbox", { name: "Skip 1 row with errors" }).check();
  await importButton.click();

  await expect(page.getByRole("status")).toHaveText(
    "Imported 1 player, released 53 to free agency, skipped 1 invalid row.");
  await expect(page.getByTestId("roster-count")).toHaveText("1");
});

test("rejects an unreadable file", async ({ page }) => {
  await page.getByRole("button", { name: "Import" }).click();
  const dialog = page.getByRole("dialog", { name: "Import roster" });
  await dialog.getByLabel("Roster file").setInputFiles({
    name: "broken.json", mimeType: "application/json", buffer: Buffer.from("{not json"),
  });
  await expect(dialog.getByRole("alert")).toContainText("Invalid JSON");
});
