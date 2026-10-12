import { expect, test } from "./support/fixtures";

test("sims a season ahead and reads the Dynasty report", async ({ page }) => {
  // A whole season, playoffs and offseason in the API's worker: ~20 s locally, more on CI.
  test.setTimeout(240_000);
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await overview.getByRole("button", { name: "Sim ahead…" }).click();
  await overview.getByLabel("Seasons").selectOption("1");
  await overview.getByRole("button", { name: "Confirm: sim ahead 1 season" }).click();
  await expect(overview.getByRole("progressbar", { name: "Simulation progress" })).toBeVisible();
  await expect(overview.getByText(/^Season 1 of 1 · 2026 · /)).toBeVisible();

  const report = overview.getByRole("status");
  await expect(report).toHaveText("Simmed 1 season · Dynasty report, 2026 →", { timeout: 180_000 });
  // On to the next preseason: the dashboard shows the offseason that just happened.
  await expect(page.getByRole("region", { name: "Offseason recap" })).toBeVisible();

  await report.click();
  await expect(page).toHaveURL(/\/dynasty\?from=2026&to=2026$/);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Dynasty report" })).toBeVisible();
  await expect(main.getByRole("article", { name: "2026 season" })).toContainText("Champion");
  await expect(main.getByRole("region", { name: "Offseason recap" })).toContainText("Ready for 2027");
});
