import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "./support/fixtures";

// WCAG 2.2 AA, checked by axe on every page: in a fresh league, and with a week played
// (box scores, stats, the Watch page). Serious and critical violations fail the test.
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function audit(page: Page, url: string): Promise<string[]> {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  // Wait for the page's content (not its loading skeleton).
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  const results = await new AxeBuilder({ page }).withTags(TAGS)
    // The 3D canvas is decorative; its information is in the page as text.
    .exclude("canvas")
    .analyze();
  // One page title (h1) per page, for screen readers' heading navigation.
  const titles = await page.getByRole("heading", { level: 1 }).count();
  const headingProblems = titles === 1 ? [] : [`${url}: ${titles} h1 headings (want 1)`];
  return [...headingProblems, ...results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${url}: ${v.id} (${v.impact}) ${v.help} — ${v.nodes.length} element(s): ` +
      v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | "))];
}

test("every page in a fresh league", async ({ page }) => {
  test.slow();
  const pages = ["/", "/roster", "/depth-chart", "/contracts", "/free-agency", "/draft", "/trades",
    "/schedule", "/playoffs", "/stats", "/league", "/history", "/leagues", "/leagues/new",
    "/account", "/coach", "/dynasty", "/game-plan"];
  const problems: string[] = [];
  for (const url of pages) problems.push(...await audit(page, url));
  expect(problems, problems.join("\n")).toEqual([]);
});

test("pages with a week played", async ({ page }) => {
  test.slow();
  const franchise = await (await page.request.get("/api/franchise")).json();
  await page.request.post(`/api/seasons/${franchise.season.id}/simulate`, { data: { until: "next_week" } });
  const schedule = await (await page.request.get(`/api/leagues/${franchise.league.id}/schedule?week=1`)).json();
  const game = schedule.games[0].id;
  const roster = await (await page.request.get(`/api/teams/${franchise.team.id}/roster`)).json();
  const pages = ["/", "/schedule?week=1", `/games/${game}`, `/games/${game}/watch?play=2`,
    "/stats", "/stats?view=teams", `/players/${roster[0].id}`];
  const problems: string[] = [];
  for (const url of pages) problems.push(...await audit(page, url));
  expect(problems, problems.join("\n")).toEqual([]);
});

test("signing in and out", async ({ browser }) => {
  const context = await browser.newContext(); // (signed out)
  const page = await context.newPage();
  const problems: string[] = [];
  for (const url of ["/signin", "/signup", "/forgot-password", "/reset-password?token=x"]) {
    problems.push(...await audit(page, url));
  }
  await context.close();
  expect(problems, problems.join("\n")).toEqual([]);
});
