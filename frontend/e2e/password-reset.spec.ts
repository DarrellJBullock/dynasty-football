import fs from "node:fs";
import path from "node:path";
import { EMAIL_OUTBOX, E2E_USER } from "./support/env";
import { expect, test } from "./support/fixtures";

/** The newest email's reset link. */
function resetLink(): string {
  const newest = fs.readdirSync(EMAIL_OUTBOX).filter((f) => f.endsWith(".eml")).sort().at(-1)!;
  const text = fs.readFileSync(path.join(EMAIL_OUTBOX, newest), "utf8");
  return text.match(/http:\/\/localhost:\d+\/reset-password\?token=\S+/)![0];
}

test("resets a forgotten password with the emailed link", async ({ page }) => {
  fs.rmSync(EMAIL_OUTBOX, { recursive: true, force: true });
  await page.goto("/");
  await page.getByRole("group", { name: "Account" }).getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/signin$/);

  await page.getByRole("link", { name: "Forgot your password?" }).click();
  const forgot = page.getByRole("form", { name: "Reset your password" });
  await forgot.getByLabel("Email").fill(E2E_USER.email);
  await forgot.getByRole("button", { name: "Email me a link" }).click();
  await expect(forgot.getByRole("status")).toContainText("a reset link is on its way");

  await page.goto(resetLink());
  const reset = page.getByRole("form", { name: "Choose a new password" });
  await reset.getByLabel("New password", { exact: true }).fill("a-brand-new-password");
  await reset.getByLabel("New password again").fill("a-brand-new-password");
  await reset.getByRole("button", { name: "Set new password" }).click();
  await expect(reset.getByRole("status")).toContainText("Your password is changed");

  await reset.getByRole("link", { name: "Sign in" }).click();
  const signIn = page.getByRole("form", { name: "Sign in" });
  await signIn.getByLabel("Email").fill(E2E_USER.email);
  await signIn.getByLabel("Password").fill("a-brand-new-password");
  await signIn.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("region", { name: "Franchise overview" })).toBeVisible();
});
