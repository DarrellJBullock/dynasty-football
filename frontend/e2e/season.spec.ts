import { expect, navigate, test } from "./support/fixtures";

const wins = (record: string) => record.split("-").map(Number).reduce((a, b) => a + b, 0);

test("sims a week, then follows the result to the box score and other pages", async ({ page }) => {
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await expect(overview.getByText("0-0", { exact: true })).toBeVisible();

  await overview.getByRole("button", { name: "Sim week 1" }).click();
  const result = overview.getByRole("status");
  await expect(result).toHaveText(/^Week 1: [WLT] \d+-\d+ (vs|@) \w+/);
  await expect(overview.getByRole("button", { name: "Sim week 2" })).toBeVisible();
  // The page refreshed in place: the record now counts one game.
  await expect(page.getByRole("region", { name: "Season" })).toContainText(/^Season[01]-[01]/);
  await expect(page.getByRole("region", { name: "Recent results" }).getByRole("listitem")).toHaveCount(1);

  await result.click();
  await expect(page).toHaveURL(/\/games\/\d+$/);
  await expect(page.getByRole("region", { name: "Scoreboard" }).getByText(/^Final/)).toBeVisible();
  const line = page.getByRole("region", { name: "Line score" });
  await expect(line.getByRole("row")).toHaveCount(3);
  await expect(page.getByRole("table", { name: "HFD passing" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Quarter 1" }).getByRole("listitem").first())
    .toContainText("kicks off");

  // Other pages show the result too (no stale client cache).
  await navigate(page, "League");
  const division = page.getByRole("region", { name: "ATL North" });
  const record = await division.getByRole("row", { name: /Hartford Ironclads/ })
    .getByRole("cell").nth(2).textContent();
  expect(wins(record!)).toBe(1);

  await navigate(page, "Schedule");
  await expect(page.getByRole("heading", { name: "Week 2" })).toBeVisible();
  await page.getByRole("navigation", { name: "Weeks" }).getByRole("link", { name: "Wk 1", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Week 1" })).toBeVisible();
  // Scoped to the visible week: Next keeps recently visited pages mounted but hidden
  // (React <Activity>), so a page-wide text search can also match the hidden game page.
  const week1 = page.getByRole("region", { name: "Week 1 games" });
  await expect(week1.getByText(/^Final/)).toHaveCount(16); // "Final" or "Final/OT"
});

test("sims the rest of the regular season from the schedule", async ({ page }) => {
  await page.goto("/schedule");
  await page.getByRole("button", { name: "Sim to end of season" }).click();
  await page.getByRole("button", { name: "Confirm: sim weeks 1–17" }).click();
  await expect(page.getByText("Regular season complete")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("status")).toContainText("Simulated 17 weeks");

  await navigate(page, "Dashboard");
  const seasonCard = page.getByRole("region", { name: "Season" });
  const record = (await seasonCard.locator(".stat-number").textContent())!;
  expect(wins(record)).toBe(17);
  await expect(page.getByRole("region", { name: "Recent results" }).getByRole("listitem")).toHaveCount(3);
});
