import { execFileSync } from "node:child_process";
import { BACKEND_DIR, E2E_DATABASE_URL, E2E_PYTHON } from "./env";

/** Bring the e2e database schema up to date, so `npm run e2e` works after migrations
 * land without a separate `make e2e` step. */
export default function globalSetup(): void {
  execFileSync(E2E_PYTHON, ["-m", "alembic", "upgrade", "head"], {
    cwd: BACKEND_DIR,
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
    stdio: "pipe",
  });
}
