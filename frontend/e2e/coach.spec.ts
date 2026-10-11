import { expect, navigate, test } from "./support/fixtures";

test("coaches the franchise's game: calls plays, hands the rest to the AI, lands on the box score", async ({ page }) => {
  // Every call replays the game on the server and loads its plays for the 3D reel.
  test.slow();
  await page.goto("/");
  await navigate(page, "Play Game");
  await expect(page).toHaveURL(/\/games\/\d+\/coach$/);
  await page.getByRole("button", { name: "Start coaching" }).click();

  const call = page.getByRole("region", { name: "Your call" });
  await expect(call.getByRole("heading", { name: /^Your (offense|defense)$/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Last play" }).locator("canvas")).toBeVisible();
  const log = page.getByRole("complementary", { name: "Play-by-play" }).getByRole("listitem");
  await expect(log).toHaveCount(1); // the opening kickoff

  // Take the AI's suggestion, then pick a play ourselves.
  await call.getByRole("button", { name: "Call it" }).click();
  await expect(log).toHaveCount(2);
  const tab = call.getByRole("tab").first();
  await tab.click();
  await call.getByRole("list", { name: "Plays" }).getByRole("button").first().click();
  await expect.poll(() => log.count()).toBeGreaterThan(2);

  // Hand the AI the rest of the game.
  await call.getByRole("button", { name: "The rest of the game" }).click();
  await call.getByRole("button", { name: "Confirm: the AI finishes the game" }).click();
  const final = page.getByRole("region", { name: "Final" });
  await expect(final.getByRole("heading")).toHaveText(/^(You won|You lost|A tie), \d+–\d+$/);

  await final.getByRole("link", { name: "Box score" }).click();
  await expect(page).toHaveURL(/\/games\/\d+$/);
  await expect(page.getByRole("region", { name: "Scoreboard" }).getByText(/^Final/)).toBeVisible();

  // With our game played, Play Game has nothing until the week is simulated.
  await navigate(page, "Play Game");
  await expect(page.getByRole("heading", { name: "No game to play" })).toBeVisible();
});
