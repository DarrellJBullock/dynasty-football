import { expect, navigate, test } from "./support/fixtures";

test("the commissioner changes the league's rules between seasons", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "League");
  const rules = page.getByRole("main").getByRole("region", { name: "League rules" });
  await expect(rules).toContainText("53 players");
  await expect(rules).toContainText("17 weeks");

  await rules.getByRole("button", { name: "Change the rules" }).click();
  await rules.getByLabel("Roster size (45–60)").fill("50");
  await rules.getByLabel("Cap growth each season (%)").fill("3");
  await rules.getByLabel("Playoff seeds per conference").selectOption("4");
  await rules.getByLabel("Regular season (weeks)").fill("10");
  await rules.getByRole("button", { name: "Save rules" }).click();
  await expect(rules.getByRole("status")).toContainText("League log");
  await expect(rules).toContainText("50 players");
  await expect(rules).toContainText("3% a season");
  await expect(rules).toContainText("4 per conference, no byes");
  await expect(rules).toContainText("10 weeks");

  // The coming season was drawn again at its new length, and AI rosters cut to 50.
  const franchise = await (await page.request.get("/api/franchise")).json();
  expect(franchise.season.weeks).toBe(10);
  const teams = await (await page.request.get(`/api/leagues/${franchise.league.id}/teams`)).json();
  const ai = teams.find((t: { id: number }) => t.id !== franchise.team.id);
  expect(ai.roster_count).toBe(50);

  await navigate(page, "League Log");
  await expect(page.getByRole("main").getByRole("region", { name: "League log entries" })
    .getByRole("listitem").first()).toContainText("Changed the league rules");

  // Once the season starts, the rules wait for the next offseason.
  await page.request.post(`/api/teams/${franchise.team.id}/cut-down`);
  expect((await page.request.post(`/api/seasons/${franchise.season.id}/simulate`,
    { data: { until: "next_week" } })).ok()).toBe(true);
  await navigate(page, "League");
  await expect(rules).toContainText("League rules change between seasons");
  await expect(rules.getByRole("button", { name: "Change the rules" })).toHaveCount(0);
});
