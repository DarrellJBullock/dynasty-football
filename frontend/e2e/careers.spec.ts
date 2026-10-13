import { backendScript, expect, navigate, test } from "./support/fixtures";

test("fired after a bad season, a general manager takes another job", async ({ page }) => {
  test.slow();
  const franchise = await (await page.request.get("/api/franchise")).json();
  // The season (a week at a time, through the API), with every owner at the end of their
  // patience before the final, so whatever happens, the owner fires the general manager.
  const sim = async () => expect((await page.request.post(
    `/api/seasons/${franchise.season.id}/simulate`, { data: { until: "next_week" } })).ok()).toBe(true);
  for (let step = 0; step < 30; step++) {
    const season = (await (await page.request.get("/api/franchise")).json()).season;
    if (season.phase === "playoffs" && season.next_round === "Championship") break;
    await sim();
  }
  backendScript(`
from app.db import SessionLocal
from app.models import Owner
with SessionLocal() as db:
    for owner in db.query(Owner):
        owner.confidence = -100
    db.commit()
`);
  await sim();

  await page.goto("/");
  const fired = page.getByRole("main").getByRole("region", { name: "Fired" });
  await expect(fired).toContainText("The owner fired you.");
  await fired.getByRole("link", { name: "See the open jobs" }).click();
  const jobs = page.getByRole("main").getByRole("region", { name: "Open jobs" });
  await expect(jobs).toContainText(`You've been fired by the ${franchise.team.full_name}`);
  const take = jobs.getByRole("button", { name: /^Take the .* job$/ }).first();
  const label = await take.getAttribute("aria-label");
  const newTeam = label!.replace(/^Take the /, "").replace(/ job$/, "");
  await take.click();
  await jobs.getByRole("button", { name: "Confirm: take this job" }).click();

  // A new team: the app starts afresh on it, and the career keeps the old one.
  await expect(page).toHaveURL("/");
  const now = await (await page.request.get("/api/franchise")).json();
  expect(now.team.full_name).toBe(newTeam);
  expect(now.fired).toBe(false);
  await navigate(page, "Career");
  const teams = page.getByRole("main").getByRole("table", { name: "Every team you've run" });
  await expect(teams.getByRole("row", { name: new RegExp(franchise.team.full_name) }))
    .toContainText("Fired");
  await expect(teams.getByRole("row", { name: new RegExp(newTeam) })).toContainText("Still there");
});
