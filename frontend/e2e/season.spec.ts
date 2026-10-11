import { expect, navigate, test } from "./support/fixtures";

const wins = (record: string) => record.split("-").map(Number).reduce((a, b) => a + b, 0);

test("sims a week, then follows the result to the box score and other pages", async ({ page }) => {
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await expect(overview.getByText("0-0", { exact: true })).toBeVisible();

  await overview.getByRole("button", { name: "Sim week 1" }).click();
  const result = overview.getByRole("status");
  await expect(result).toHaveText(/^Week 1: [WLT] \d+-\d+ (vs|@) \w+/);
  await expect(overview.getByRole("button", { name: "Sim week 2" })).toBeVisible();
  // The page refreshed in place: the record now counts one game.
  await expect(page.getByRole("region", { name: "Season" })).toContainText(/^Season[01]-[01]/);
  await expect(page.getByRole("region", { name: "Recent results" }).getByRole("listitem")).toHaveCount(1);

  await result.click();
  await expect(page).toHaveURL(/\/games\/\d+$/);
  await expect(page.getByRole("region", { name: "Scoreboard" }).getByText(/^Final/)).toBeVisible();
  const line = page.getByRole("region", { name: "Line score" });
  await expect(line.getByRole("row")).toHaveCount(3);
  await expect(page.getByRole("table", { name: "HFD passing" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Quarter 1" }).getByRole("listitem").first())
    .toContainText("kicks off");

  // Other pages show the result too (no stale client cache).
  await navigate(page, "League");
  const division = page.getByRole("region", { name: "ATL North" });
  const record = await division.getByRole("row", { name: /Hartford Ironclads/ })
    .getByRole("cell").nth(2).textContent();
  expect(wins(record!)).toBe(1);

  await navigate(page, "Schedule");
  await expect(page.getByRole("heading", { name: "Week 2" })).toBeVisible();
  await page.getByRole("navigation", { name: "Weeks" }).getByRole("link", { name: "Wk 1", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Week 1" })).toBeVisible();
  // Scoped to the visible week: Next keeps recently visited pages mounted but hidden
  // (React <Activity>), so a page-wide text search can also match the hidden game page.
  const week1 = page.getByRole("region", { name: "Week 1 games" });
  await expect(week1.getByText(/^Final/)).toHaveCount(16); // "Final" or "Final/OT"
});

test("sims a season and playoffs to a champion, then starts the next season", async ({ page }) => {
  // A whole season, the playoffs, re-signing, and free agency: ~45 s on CI runners.
  test.slow();
  await page.goto("/playoffs");
  await expect(page.getByText(/if the season ended today/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Bracket" })).toHaveCount(0);

  // The season sims in the background: leave it running and find it on the Dashboard.
  await page.goto("/schedule");
  await page.getByRole("button", { name: "Sim to end of season" }).click();
  await page.getByRole("button", { name: "Confirm: sim weeks 1–17" }).click();
  await expect(page.getByRole("main").getByRole("progressbar", { name: "Simulation progress" })).toBeVisible();
  await navigate(page, "Dashboard");
  const simulation = page.getByRole("region", { name: "Franchise overview" });
  await expect(simulation.getByRole("progressbar", { name: "Simulation progress" })).toBeVisible();
  await expect(simulation.getByRole("button", { name: "Sim Wild Card" })).toBeVisible({ timeout: 30_000 });
  await expect(simulation.getByRole("status")).toContainText("Simulated 17 weeks");

  const seasonCard = page.getByRole("region", { name: "Season" });
  const record = (await seasonCard.locator(".stat-number").textContent())!;
  expect(wins(record)).toBe(17);
  await expect(page.getByRole("region", { name: "Recent results" }).getByRole("listitem")).toHaveCount(3);

  await navigate(page, "Playoffs");
  for (const conference of ["Atlantic Conference", "Pacific Conference"]) {
    await expect(page.getByRole("region", { name: `${conference} seeds` }).getByRole("listitem")).toHaveCount(7);
  }
  const bracket = page.getByRole("region", { name: "Bracket" });
  await expect(bracket.getByRole("group", { name: "Wild Card" }).getByRole("link")).toHaveCount(6);
  await expect(bracket.getByRole("group", { name: "Divisional" })).toContainText("TBD");

  await page.getByRole("button", { name: "Sim Wild Card" }).click();
  await expect(page.getByRole("button", { name: "Sim Divisional" })).toBeVisible();
  await expect(bracket.getByRole("group", { name: "Divisional" }).getByRole("link")).toHaveCount(4);

  await page.getByRole("button", { name: "Sim rest of playoffs" }).click();
  await page.getByRole("button", { name: "Confirm: sim to a champion" }).click();
  const champion = page.getByRole("region", { name: "Champion" });
  await expect(champion).toContainText(/\d{4} champions/);
  const final = bracket.getByRole("group", { name: "Championship", exact: true }).getByRole("link");
  await expect(final).toContainText("Final");
  await final.click();
  await expect(page.getByText(/Championship · Neutral site/)).toBeVisible();
  await expect(page.getByRole("link", { name: "← Playoff bracket" })).toBeVisible();

  // The season goes into the history books, with its awards.
  await navigate(page, "History");
  const archived = page.getByRole("article", { name: /^\d{4} season$/ }).first();
  await expect(archived).toContainText("Champion");
  await expect(archived.getByRole("list", { name: /awards$/ }).getByRole("listitem")).toHaveCount(5);
  await expect(page.getByRole("group", { name: "Passing yards" }).getByRole("listitem")).toHaveCount(5);

  // Re-sign an expiring player before the rollover.
  await navigate(page, "Contracts");
  await expect(page.getByText(/Re-signing is open/)).toBeVisible();
  const expiring = page.getByRole("region", { name: "Expiring contracts" });
  const firstRow = expiring.getByRole("row").nth(1);
  await firstRow.getByRole("button", { name: /^Negotiate with / }).click();
  const dialog = page.getByRole("dialog", { name: /^Re-sign / });
  await dialog.getByRole("button", { name: /^Offer / }).click(); // asking price, preferred length
  await expect(dialog.getByRole("status")).toContainText("signs for");
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(firstRow).toContainText("Re-signed");

  // The offseason rolls the league into next year.
  await navigate(page, "Dashboard");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await overview.getByRole("button", { name: "Start free agency" }).click();
  await overview.getByRole("button", { name: "Confirm: run the offseason" }).click();
  const recap = page.getByRole("region", { name: "Offseason recap" });
  await expect(recap).toContainText(/\d{4} offseason/, { timeout: 30_000 });
  await expect(recap.getByRole("group", { name: "Re-signed" })).toBeVisible();

  // Free agency: outbid everyone for a kicker on day 1, then let the market run out.
  await navigate(page, "Free Agency");
  await expect(page.getByText(/Day 1 of 5/)).toBeVisible();
  const agents = page.getByRole("region", { name: "Free agents" });
  await agents.getByLabel("Position").selectOption("K");
  await agents.getByRole("button", { name: /^Make an offer to / }).first().click();
  const offer = page.getByRole("dialog", { name: /^Offer / });
  await offer.getByLabel("Salary per year ($M)").fill("5");
  await offer.getByRole("button", { name: /^Offer \$5\.0M/ }).click();
  await expect(agents.getByText(/Leading/)).toBeVisible();
  const controls = page.getByRole("group", { name: "Free agency" });
  await controls.getByRole("button", { name: "Play free agency day 1" }).click();
  await expect(controls.getByRole("status")).toContainText("you signed");
  await controls.getByRole("button", { name: "Finish free agency" }).click();
  await controls.getByRole("button", { name: "Confirm: finish free agency" }).click();
  await expect(controls).toBeHidden({ timeout: 30_000 }); // the market closes; the draft opens

  // The draft: scout the top prospect, sim to our pick, take him, then let it finish.
  await navigate(page, "Draft");
  const status = page.getByRole("status", { name: "Draft status" });
  await expect(status).toContainText(/On the clock|You're on the clock/);
  const board = page.getByRole("region", { name: "Prospects" });
  const scoutedName = (await board.getByRole("button", { name: /^Scout / }).first()
    .getAttribute("aria-label"))!.replace(/^Scout /, "");
  // Click him by name: `.first()` re-resolves at click time and could land on someone else.
  const scout = board.getByRole("button", { name: `Scout ${scoutedName}`, exact: true });
  await scout.click();
  // Scouted: his exact rating replaces the range (and the board re-sorts).
  await expect(scout).toHaveCount(0);
  const draftControls = page.getByRole("group", { name: "Draft" });
  await draftControls.getByRole("button", { name: "Sim to my pick" }).click();
  await expect(status).toContainText("You're on the clock");
  const choice = board.getByRole("row").nth(1);
  const name = (await choice.getByRole("button", { name: /^Draft / }).getAttribute("aria-label"))!
    .replace(/^Draft /, "");
  await choice.getByRole("button", { name: /^Draft / }).click();
  await expect(page.getByRole("region", { name: "Your picks" })).toContainText(name);
  await draftControls.getByRole("button", { name: "Finish draft" }).click();
  await draftControls.getByRole("button", { name: "Confirm: finish the draft (auto-pick for me)" }).click();
  await expect(status).toHaveText("The draft is complete.");
  const cutDown = page.getByRole("region", { name: "Roster cut-down" });
  if (await cutDown.isVisible()) {
    await cutDown.getByRole("button", { name: /^Auto-cut to/ }).click();
    await expect(cutDown).toHaveCount(0);
  }

  await navigate(page, "Dashboard");
  await expect(recap.getByRole("group", { name: "New arrivals" })).toContainText("FA ·");
  await expect(recap.getByRole("group", { name: "New arrivals" })).toContainText("Draft R1");
  await expect(overview.getByText("0-0", { exact: true })).toBeVisible();

  await overview.getByRole("button", { name: "Sim week 1" }).click();
  await expect(overview.getByRole("status")).toHaveText(/^Week 1: /);
  await expect(recap).toHaveCount(0);
});
