import { expect, test } from "./support/fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/roster");
  await expect(page.getByTestId("roster-count")).toHaveText("53");
});

test("filters and searches the roster", async ({ page }) => {
  const rows = page.getByRole("table").locator("tbody tr");
  await page.getByRole("tab", { name: /^QB/ }).click();
  await expect(rows).toHaveCount(3);
  await page.getByRole("tab", { name: /^All/ }).click();
  await page.getByRole("searchbox", { name: "Search roster" }).fill("quarles");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Keegan Quarles");
});

test("edits a player's ratings and the overall updates", async ({ page }) => {
  await page.getByRole("button", { name: "Keegan Quarles" }).click();
  const panel = page.getByRole("dialog", { name: "Player details" });
  await expect(panel.getByTitle("82 overall (great)")).toBeVisible();

  await panel.getByRole("button", { name: "Edit player" }).click();
  await panel.getByRole("slider", { name: "Throw Power" }).fill("97");
  await panel.getByRole("button", { name: "Save changes" }).click();

  await expect(page.getByRole("status")).toHaveText(/Saved Keegan Quarles/);
  await expect(panel.getByTitle("87 overall (great)")).toBeVisible();

  // Persisted: still 87 after a full reload.
  await page.reload();
  const row = page.getByRole("row", { name: /Keegan Quarles/ });
  await expect(row.getByTitle("87 overall (great)")).toBeVisible();
});

test("releases a player and signs him back from free agency", async ({ page }) => {
  await page.getByRole("button", { name: "Keegan Quarles" }).click();
  const panel = page.getByRole("dialog", { name: "Player details" });
  await panel.getByRole("button", { name: "Release" }).click();
  await expect(panel.getByRole("status")).toContainText("of dead money");
  await panel.getByRole("button", { name: "Confirm release" }).click();
  await expect(page.getByRole("status")).toHaveText(/Keegan Quarles was released/);
  await expect(page.getByTestId("roster-count")).toHaveText("52");

  await page.getByRole("button", { name: "Free agents" }).click();
  const dialog = page.getByRole("dialog", { name: "Free agents" });
  await dialog.getByRole("button", { name: "Sign Keegan Quarles" }).click();
  await expect(dialog.getByText("Your roster is full.")).toBeVisible();
  await page.keyboard.press("Escape");

  await expect(page.getByTestId("roster-count")).toHaveText("53");
  await expect(page.getByRole("button", { name: "Keegan Quarles" })).toBeVisible();
});
