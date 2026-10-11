import { expect, navigate, test } from "./support/fixtures";

test("leaders, player pages, and team stats after a simulated week", async ({ page }) => {
  await page.goto("/stats");
  const passing = page.getByRole("region", { name: "Passing yards" });
  await expect(passing).toContainText("No games played yet.");

  await navigate(page, "Dashboard");
  await page.getByRole("region", { name: "Franchise overview" }).getByRole("button", { name: "Sim week 1" }).click();
  await expect(page.getByRole("region", { name: "Franchise overview" }).getByRole("status")).toBeVisible();

  await navigate(page, "Stats");
  await expect(passing.getByRole("listitem")).toHaveCount(5);
  const leader = passing.getByRole("listitem").first().getByRole("link");
  const name = (await leader.textContent())!;
  await leader.click();

  await expect(page).toHaveURL(/\/players\/\d+$/);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByRole("region", { name: "Season totals" })).toContainText("1 game");
  const log = page.getByRole("region", { name: "Game log" });
  await expect(log.getByRole("row")).toHaveCount(2);
  await log.getByRole("link", { name: /^[WLT] \d+-\d+/ }).click();
  await expect(page).toHaveURL(/\/games\/\d+$/);

  // Box score names link back to player pages.
  const boxPlayer = page.getByRole("table", { name: /passing$/ }).first().getByRole("link").first();
  await boxPlayer.click();
  await expect(page).toHaveURL(/\/players\/\d+$/);

  await navigate(page, "Stats");
  await page.getByRole("tab", { name: "Teams" }).click();
  const teams = page.getByRole("region", { name: "Team stats" });
  await expect(teams.getByRole("row")).toHaveCount(33);
  await teams.getByRole("button", { name: "PA/G" }).click();
  await expect(teams.getByRole("columnheader", { name: /PA\/G/ })).toHaveAttribute("aria-sort", "ascending");

  await page.getByRole("tab", { name: "Leaders" }).click();
  await page.getByRole("region", { name: "Rushing yards" }).getByRole("link", { name: "Top 25 →" }).click();
  await expect(page.getByRole("region", { name: "Rushing yards leaders" }).getByRole("row")).toHaveCount(26);
});
