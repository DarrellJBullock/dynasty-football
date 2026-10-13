import { expect, navigate, test } from "./support/fixtures";

test("the locker room's least happy player, and what's moved his mood", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "Roster");
  const room = page.getByRole("main").getByRole("region", { name: "Locker room" });
  await expect(room.getByRole("meter", { name: "Average mood" })).toBeVisible();
  const least = room.getByRole("list", { name: "Least happy" }).getByRole("link").first();
  const name = await least.textContent();
  await least.click();

  await expect(page.getByRole("main").getByRole("heading", { level: 1, name: name! })).toBeVisible();
  const panel = page.getByRole("main").getByRole("region", { name: "Personality and mood" });
  await expect(panel).toContainText("Drive:");
  await expect(panel).toContainText("Temperament:");
  await expect(panel.getByRole("list", { name: "What moved his mood" }))
    .toContainText("Coming into the season");
});
