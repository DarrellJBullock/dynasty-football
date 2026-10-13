import { readFile } from "node:fs/promises";
import { expect, test } from "./support/fixtures";

test("a commissioner shares a read-only link, a visitor follows the league, and sharing stops", async ({ page, browser }) => {
  const franchise = await (await page.request.get("/api/franchise")).json();
  await page.request.post(`/api/seasons/${franchise.season.id}/simulate`, { data: { until: "next_week" } });

  // The commissioner makes the link on the Members page.
  await page.goto("/members");
  const panel = page.getByRole("main").getByRole("region", { name: "Share and export" });
  await panel.getByRole("button", { name: "Share a read-only link" }).click();
  const link = await panel.getByLabel("Public link (shown once)").inputValue();
  expect(link).toMatch(/\/share\/[\w-]+$/);

  // A visitor without an account: the standings, then a week's games, then a box score.
  const context = await browser.newContext();
  const visitor = await context.newPage();
  await visitor.goto(link);
  const main = visitor.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: franchise.league.name })).toBeVisible();
  await expect(visitor.getByRole("navigation", { name: "League" })).toBeVisible();
  await expect(visitor.getByRole("navigation", { name: "Main" })).toHaveCount(0); // (no game sidebar)
  await visitor.getByRole("navigation", { name: "League" }).getByRole("link", { name: "Schedule" }).click();
  await main.getByRole("link", { name: "Wk 1", exact: true }).click();
  await expect(visitor).toHaveURL(/schedule\?week=1$/);
  await expect(main.getByRole("region", { name: "Week 1 games" })).toBeVisible();
  await expect(main.getByRole("button")).toHaveCount(0); // (nothing to sim)
  await main.getByRole("link", { name: / at / }).first().click();
  await expect(visitor).toHaveURL(/\/share\/[\w-]+\/games\/\d+$/);
  await expect(main.getByRole("region", { name: "Line score" })).toBeVisible();
  await expect(main.locator('a[href^="/players/"]')).toHaveCount(0); // (no player pages)

  // Every member can download the whole league.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    panel.getByRole("link", { name: "Download the league (JSON)" }).click(),
  ]);
  const data = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(data.format).toBe("dynasty-football/league");
  expect(data.league.name).toBe(franchise.league.name);
  expect(data.games.some((g: { status: string }) => g.status === "final")).toBe(true);

  // Sharing stops: the link doesn't work any more.
  await panel.getByRole("button", { name: "Stop sharing" }).click();
  await expect(panel).toContainText("Not shared.");
  await visitor.goto(link);
  await expect(visitor.getByRole("main")).toContainText("isn't shared any more");
  await context.close();
});
