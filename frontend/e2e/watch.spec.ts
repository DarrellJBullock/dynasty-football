import { expect, navigate, test } from "./support/fixtures";

test("watches a play in 3D from the play-by-play, then steps through the game", async ({ page }) => {
  test.slow(); // 3D on CI renders in software: every click waits on a busy frame loop
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await overview.getByRole("button", { name: "Sim week 1" }).click();
  const result = overview.getByRole("status");
  await expect(result).toHaveText(/^Week 1: /);
  await result.click();
  await expect(page).toHaveURL(/\/games\/\d+$/);
  const gameUrl = page.url();

  await page.getByRole("list", { name: "Quarter 1" }).getByRole("link", { name: "Watch play 2", exact: true }).click();
  await expect(page).toHaveURL(/\/games\/\d+\/watch\?play=2$/);
  const viewer = page.getByRole("region", { name: "Play viewer" });
  await expect(viewer.locator("canvas")).toBeVisible();
  await expect(viewer.getByText(/^Play 2 of \d+ · \w+ 1st & 10 at /)).toBeVisible();
  // The broadcast score bug, with the clock and the down.
  const bug = viewer.getByRole("group", { name: "Score bug" });
  await expect(bug).toBeVisible();
  await expect(bug.getByTestId("down")).toHaveText("1st & 10");
  await expect(bug.getByTestId("game-clock")).toHaveText(/^\d+:\d\d$/);

  // It plays on its own: the playhead moves, then pausing and scrubbing take over.
  const scrubber = viewer.getByRole("slider", { name: "Play timeline" });
  await expect.poll(async () => Number(await scrubber.inputValue()), { timeout: 15_000 }).toBeGreaterThan(0.3);
  await viewer.getByRole("button", { name: "Pause", exact: true }).click();
  await scrubber.fill("1.2");
  await expect(viewer.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await expect(viewer.getByRole("status")).toHaveText("Snap");

  // Step to the next play; the play list follows.
  await viewer.getByRole("button", { name: "Next play ›" }).click();
  await expect(page).toHaveURL(/\?play=3$/);
  await expect(viewer.getByText(/^Play 3 of /)).toBeVisible();
  const plays = page.getByRole("complementary", { name: "Plays" });
  await expect(plays.locator('[aria-current="true"]')).toContainText(await viewer.getByTestId("play-text").innerText());

  // Pick the opening kickoff from the list, then head back to the box score.
  await plays.getByRole("button", { name: /kicks off/ }).first().click();
  await expect(page).toHaveURL(/\?play=1$/);
  await expect(viewer.getByText(/^Play 1 of \d+ · \w+ kicks off$/)).toBeVisible();
  await page.getByRole("link", { name: "← Box score" }).click();
  await expect(page).toHaveURL(gameUrl);
});

test("watches a game from the schedule, straight through or just the highlights", async ({ page }) => {
  test.slow(); // 3D on CI renders in software: every click waits on a busy frame loop
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await overview.getByRole("button", { name: "Sim week 1" }).click();
  await expect(overview.getByRole("status")).toHaveText(/^Week 1: /);

  await navigate(page, "Schedule");
  await page.getByRole("navigation", { name: "Weeks" }).getByRole("link", { name: "Wk 1", exact: true }).click();
  const week = page.getByRole("region", { name: "Week 1 games" });
  await week.getByRole("link", { name: /^Watch / }).first().click();
  await expect(page).toHaveURL(/\/games\/\d+\/watch\?play=1&auto=1$/);
  const viewer = page.getByRole("region", { name: "Play viewer" });
  await expect(viewer.getByRole("checkbox", { name: "Play straight through" })).toBeChecked();

  await viewer.getByRole("checkbox", { name: /^Highlights only \(\d+\)$/ }).check();
  await expect(viewer.getByText(/^Highlight 1 of \d+ · Play \d+ of /)).toBeVisible();
  await expect(page).toHaveURL(/highlights=1/);
  const list = page.getByRole("complementary", { name: "Plays" });
  await expect(list.getByRole("heading", { name: "Highlights" })).toBeVisible();
  await viewer.getByRole("button", { name: "Next play ›" }).click();
  await expect(viewer.getByText(/^Highlight 2 of \d+/)).toBeVisible();
});
