import { expect, navigate, test } from "./support/fixtures";

// Regression: the client router reused previously visited pages, so data changed on
// one page showed stale on another until a full reload.

test("dashboard reflects a roster edit made on another page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTitle("79 overall (good)").first()).toBeVisible();

  await navigate(page, "Roster");
  await page.getByRole("button", { name: "Keegan Quarles" }).click();
  const panel = page.getByRole("dialog", { name: "Player details" });
  await panel.getByRole("button", { name: "Release" }).click();
  await panel.getByRole("button", { name: "Confirm release" }).click();
  await expect(page.getByTestId("roster-count")).toHaveText("52");

  await navigate(page, "Dashboard");
  await expect(page.getByRole("region", { name: "Active roster" })).toContainText("52/53");
  await expect(page.getByRole("region", { name: "Franchise overview" }).getByTitle(/^78 overall/)).toBeVisible();
});

test("depth chart changes show on the dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Franchise overview" }).getByTitle(/^79 overall/)).toBeVisible();
  await navigate(page, "Depth Chart");
  await page.getByRole("button", { name: "Move Kobe Sterling up" }).click();
  await expect(page.getByTitle("Offense 77")).toBeVisible();

  await navigate(page, "Dashboard");
  await expect(page.getByRole("region", { name: "Franchise overview" }).getByTitle(/^78 overall/)).toBeVisible();
});

test("My Leagues reflects a league created after it was visited", async ({ page }) => {
  await page.goto("/leagues");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(1);
  await page.getByRole("link", { name: "+ Create league" }).click();
  await page.getByRole("combobox", { name: "Conferences" }).selectOption("1");
  await page.getByRole("combobox", { name: "Divisions per conference" }).selectOption("2");
  await page.getByRole("combobox", { name: "Teams per division" }).selectOption("2");
  await expect(page.getByTestId("builder-team")).toHaveCount(4);
  await page.getByRole("radio", { name: "Play as Albany Sentinels" }).check();
  await page.getByRole("button", { name: "Create league" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sentinels" })).toBeVisible();

  await navigate(page, "My Leagues");
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("listitem", { name: "Sentinels Dynasty" })).toContainText("Active");
});
