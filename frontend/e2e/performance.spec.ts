import type { Page } from "@playwright/test";
import { expect, test } from "./support/fixtures";

// Page budgets on the production build (docs/design/platform.md §7): Largest Contentful
// Paint under 2.5 s and cumulative layout shift under 0.1.
const LCP_MS = 2500;
const CLS = 0.1;

declare global {
  interface Window { __vitals: { lcp: number; cls: number } }
}

async function vitals(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  await page.waitForTimeout(300); // (late shifts)
  return page.evaluate(() => window.__vitals);
}

test("key pages load within budget", async ({ page }) => {
  test.slow();
  await page.addInitScript(() => {
    window.__vitals = { lcp: 0, cls: 0 };
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__vitals.lcp = entry.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
        if (!entry.hadRecentInput) window.__vitals.cls += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  const franchise = await (await page.request.get("/api/franchise")).json();
  await page.request.post(`/api/seasons/${franchise.season.id}/simulate`, { data: { until: "next_week" } });
  const schedule = await (await page.request.get(`/api/leagues/${franchise.league.id}/schedule?week=1`)).json();
  const game = schedule.games[0].id;

  const results: string[] = [];
  for (const url of ["/", "/roster", "/schedule?week=1", `/games/${game}`, `/games/${game}/watch?play=2`]) {
    const { lcp, cls } = await vitals(page, url);
    results.push(`${url}: LCP ${Math.round(lcp)} ms, CLS ${cls.toFixed(3)}`);
    expect.soft(lcp, `${url} LCP`).toBeLessThan(LCP_MS);
    expect.soft(cls, `${url} CLS`).toBeLessThan(CLS);
  }
  console.log(results.join("\n"));
});

test("three.js loads only on pages with a 3D view", async ({ page }) => {
  const scripts: string[] = [];
  page.on("response", async (response) => {
    if (response.url().includes("/_next/static/") && response.url().endsWith(".js")) {
      scripts.push(await response.text().catch(() => ""));
    }
  });
  await page.goto("/roster");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(scripts.length).toBeGreaterThan(0);
  expect(scripts.some((js) => js.includes("WebGLRenderer"))).toBe(false);

  // (and the check can see it: the dashboard's 3D field loads it)
  scripts.length = 0;
  await page.goto("/");
  await expect(page.getByRole("img", { name: "3D field preview" }).locator("canvas")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(scripts.some((js) => js.includes("WebGLRenderer"))).toBe(true);
});
