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

  // Each card says what that staff member does at his rating.
  await expect(staff.getByRole("article", { name: "Head trainer" })).toContainText(/come back \d+% (sooner|later)/);

  // The coaching carousel: let our scout go, then hire another off the market.
  const scout = staff.getByRole("article", { name: "Scout" });
  await scout.getByRole("button", { name: "Let go" }).click();
  await expect(main.getByRole("status")).toContainText("What's left of the contract is owed");
  await expect(staff.getByRole("article", { name: "Scout (open)" })).toBeVisible();
  await expect(main.getByText(/owed to staff let go/)).toBeVisible();
  const market = main.getByRole("table", { name: "Staff on the market" });
  const hire = market.getByRole("row").filter({ hasText: "Scout" }).first().getByRole("button", { name: /^Hire / });
  const name = (await hire.getAttribute("aria-label"))!.replace(/^Hire /, "");
  await hire.click();
  await expect(main.getByRole("status")).toContainText(`${name} is your new scout`);
  await expect(staff.getByRole("article", { name: "Scout" })).toContainText(name);

  // A player's page says what his coaches do for him.
  const roster = await (await page.request.get(`/api/teams/${franchise.team.id}/roster`)).json();
  const qb = roster.find((p: { position: string }) => p.position === "QB");
  await page.goto(`/players/${qb.id}`);
  const coaching = main.getByRole("region", { name: "Coaching" });
  await expect(coaching).toContainText("Offensive coordinator:");
  await expect(coaching).toContainText(/Injured players come back/);
  await page.goBack();

  // Another team's staff.
  const other = teams.find((t: { id: number }) => t.id !== franchise.team.id);
  await main.getByLabel("Team").selectOption(String(other.id));
  await expect(page).toHaveURL(new RegExp(`/staff\\?team=${other.id}$`));
  await expect(main.getByRole("heading", { level: 1, name: other.full_name })).toBeVisible();
});
