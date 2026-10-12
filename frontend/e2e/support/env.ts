import os from "node:os";
import path from "node:path";

export const API_PORT = 8001;
export const WEB_PORT = 3001;
export const API_URL = `http://localhost:${API_PORT}`;
export const BACKEND_DIR = path.resolve(__dirname, "../../../backend");
export const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL ?? "postgresql+psycopg://localhost:5432/dynasty_football_e2e";
// Python with the backend installed: the local venv by default, plain `python` in CI.
export const E2E_PYTHON = process.env.E2E_PYTHON ?? path.join(BACKEND_DIR, ".venv/bin/python");
// The account the seeded league belongs to; every test starts signed in as it.
export const E2E_USER = { email: "e2e@example.test", password: "e2e-test-password" };
// The e2e API writes emails (password resets) here instead of sending them.
export const EMAIL_OUTBOX = path.join(os.tmpdir(), "dynasty-e2e-outbox");
