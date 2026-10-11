import { expect, test } from "./support/fixtures";

test("watches a play in 3D from the play-by-play, then steps through the game", async ({ page }) => {
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
