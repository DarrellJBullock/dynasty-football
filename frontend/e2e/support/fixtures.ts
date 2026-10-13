import { execFileSync } from "node:child_process";
import { test as base, expect, type Page } from "@playwright/test";
import { BACKEND_DIR, E2E_DATABASE_URL, E2E_PYTHON, E2E_USER } from "./env";

/** Wipe the e2e database and regenerate the sample league (seed 2026), owned by E2E_USER. */
export function resetDatabase(): void {
  execFileSync(E2E_PYTHON, ["-m", "app.seed", "--reset", "--seed", "2026"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL, DEV_USER_EMAIL: E2E_USER.email,
      DEV_USER_PASSWORD: E2E_USER.password },
    stdio: "pipe",
  });
}

/**
 * Run Python against the e2e database (backend code importable), for setup the game
 * can't reach in a test's time, such as a career long enough for the Hall of Fame.
 * Returns its stdout.
 */
export function backendScript(code: string): string {
  return execFileSync(E2E_PYTHON, ["-c", code], {
    cwd: BACKEND_DIR,
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
    encoding: "utf8",
  });
}

/**
 * Every test starts from a freshly seeded league, signed in as its owner, and fails if
 * the page throws an uncaught error (React render errors, hydration failures, etc.).
 */
export const test = base.extend<{ freshLeague: void; signedIn: void; pageErrors: string[] }>({
  freshLeague: [
    async ({}, use) => {
      resetDatabase();
      await use();
    },
    { auto: true },
  ],
  signedIn: [
    async ({ freshLeague, page }, use) => {
      void freshLeague; // (after the reset, which recreates the account)
      // Through the web app's /api, so the session cookie lands in the browser context.
      const response = await page.request.post("/api/auth/signin", { data: E2E_USER });
      expect(response.ok(), await response.text()).toBe(true);
      await use();
    },
    { auto: true },
  ],
  pageErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await use(errors);
      expect(errors, "uncaught errors in the page").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** Sidebar navigation, scoped so page content with the same text doesn't match. */
export async function navigate(page: Page, label: string): Promise<void> {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true }).click();
}
