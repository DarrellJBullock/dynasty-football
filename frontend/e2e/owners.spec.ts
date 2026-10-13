import { expect, test } from "./support/fixtures";

test("the owner sets goals for the season and reviews it at the end", async ({ page }) => {
  test.slow();
  await page.goto("/");
  const card = page.getByRole("main").getByRole("region", { name: "The owner" });
  await expect(card).toContainText(/wants (to win now|something that lasts|the team to pay its way)/);
  await expect(card.getByRole("list", { name: "Goals" }).getByRole("listitem")).not.toHaveCount(0);
  await expect(card.getByRole("meter", { name: "Owner confidence" })).toHaveAttribute("aria-valuenow", "60");

  // A whole season (through the API: simming has its own spec), then the owner's review.
  const franchise = await (await page.request.get("/api/franchise")).json();
  for (const until of ["end_of_regular_season", "end_of_playoffs"]) {
    expect((await page.request.post(`/api/seasons/${franchise.season.id}/simulate`,
      { data: { until } })).ok()).toBe(true);
  }
  await page.reload();
  const review = card.getByText(new RegExp(`${franchise.season.year} review: the owner `));
  await expect(review).toBeVisible();
  await review.click();
  await expect(card.getByRole("list", { name: "What moved the owner" })).toContainText("Fan mood");
  const owner = await (await page.request.get(`/api/teams/${franchise.team.id}/owner`)).json();
  await expect(card.getByRole("meter", { name: "Owner confidence" }))
    .toHaveAttribute("aria-valuenow", String(owner.confidence));
});
