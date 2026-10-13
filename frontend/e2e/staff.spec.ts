import { expect, navigate, test } from "./support/fixtures";

test("the staff page: our coaches, scout and trainer, another team's, and the league's head coaches", async ({ page }) => {
  const franchise = await (await page.request.get("/api/franchise")).json();
  await page.goto("/");
  await navigate(page, "Staff");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: franchise.team.full_name })).toBeVisible();
  const staff = main.getByRole("region", { name: "Coaches and staff" });
  for (const role of ["Head coach", "Offensive coordinator", "Defensive coordinator", "Scout", "Head trainer"]) {
    await expect(staff.getByRole("article", { name: role })).toContainText("Rating");
  }
  const heads = main.getByRole("table", { name: "Head coaches" });
  const teams = await (await page.request.get(`/api/leagues/${franchise.league.id}/teams`)).json();
  await expect(heads.getByRole("row")).toHaveCount(teams.length + 1);

  // Another team's staff.
  const other = teams.find((t: { id: number }) => t.id !== franchise.team.id);
  await main.getByLabel("Team").selectOption(String(other.id));
  await expect(page).toHaveURL(new RegExp(`/staff\\?team=${other.id}$`));
  await expect(main.getByRole("heading", { level: 1, name: other.full_name })).toBeVisible();
});
