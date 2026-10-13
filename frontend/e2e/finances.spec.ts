import { expect, navigate, test } from "./support/fixtures";

test("sets the ticket price, then follows the money through the season", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "Finances");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Finances" })).toBeVisible();
  await expect(main.getByText("No home game played yet this season.")).toBeVisible();

  const prices = main.getByRole("radiogroup", { name: "Ticket price" });
  await prices.getByRole("radio", { name: /Low/ }).click();
  await expect(prices.getByRole("radio", { name: /Low/ })).toHaveAttribute("aria-checked", "true");

  // Four weeks (through the API: simming has its own spec): two or so home games.
  const franchise = await (await page.request.get("/api/franchise")).json();
  for (let week = 0; week < 4; week++) {
    expect((await page.request.post(`/api/seasons/${franchise.season.id}/simulate`,
      { data: { until: "next_week" } })).ok()).toBe(true);
  }
  await page.reload();
  const finances = await (await page.request.get(`/api/teams/${franchise.team.id}/finances`)).json();
  expect(finances.gates.length).toBeGreaterThan(0);
  const games = main.getByRole("table", { name: "Each home game's gate" });
  await expect(games.getByRole("row")).toHaveCount(finances.gates.length + 1);
  await expect(main.getByRole("region", { name: "Profit so far" })).toBeVisible();
  // Once the season's under way, the price waits for the next one.
  await expect(main.getByText(/Ticket prices are set before the season/)).toBeVisible();
  await expect(prices.getByRole("radio", { name: /High/ })).toBeDisabled();
});
