import { execFileSync } from "node:child_process";
import { test as base, expect, type Page } from "@playwright/test";
import { BACKEND_DIR, E2E_DATABASE_URL, E2E_PYTHON } from "./env";

/** Wipe the e2e database and regenerate the sample league (seed 2026). */
export function resetDatabase(): void {
  execFileSync(E2E_PYTHON, ["-m", "app.seed", "--reset", "--seed", "2026"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
    stdio: "pipe",
  });
}

/**
 * Every test starts from a freshly seeded league, and fails if the page throws an
 * uncaught error (React render errors, hydration failures, etc.).
 */
export const test = base.extend<{ freshLeague: void; pageErrors: string[] }>({
  freshLeague: [
    async ({}, use) => {
      resetDatabase();
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
