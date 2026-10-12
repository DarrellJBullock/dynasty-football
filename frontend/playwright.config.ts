import { defineConfig, devices } from "@playwright/test";
import { API_PORT, API_URL, BACKEND_DIR, E2E_DATABASE_URL, E2E_PYTHON, WEB_PORT } from "./e2e/support/env";

// End-to-end tests run the real app against a dedicated database on their own ports,
// so they never touch your dev servers (3000/8000) or dev data.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/support/global-setup.ts",
  // Every test reseeds the shared e2e database, so tests run one at a time.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `"${E2E_PYTHON}" -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: BACKEND_DIR,
      url: `${API_URL}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        DATABASE_URL: E2E_DATABASE_URL,
        ALLOWED_ORIGINS: JSON.stringify([`http://localhost:${WEB_PORT}`]),
        WORKER_EMBEDDED: "1", // background jobs run in a thread of the API
      },
    },
    {
      command: `npx next build && npx next start --port ${WEB_PORT}`,
      cwd: __dirname,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: {
        NEXT_DIST_DIR: ".next-e2e",
        API_URL, // server components call it, and /api is proxied to it
      },
    },
  ],
});
