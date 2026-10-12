import { E2E_USER } from "./support/env";
import { expect, test } from "./support/fixtures";

test("signs in, skips to the page and sims a week with the keyboard alone", async ({ browser }) => {
  const context = await browser.newContext(); // (signed out)
  const page = await context.newPage();
  await page.goto("/signin");
  // (The form streams in after the shell; wait for it, and for React to take it over,
  // before typing.)
  await expect(page.getByRole("form", { name: "Sign in" })).toBeVisible();
  await page.waitForLoadState("networkidle");

  // The form, in order: email, password, Sign in.
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Email")).toBeFocused();
  await page.keyboard.type(E2E_USER.email);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password")).toBeFocused();
  await page.keyboard.type(E2E_USER.password);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Franchise overview" })).toBeVisible();
  await page.waitForLoadState("networkidle");

  // The first Tab reaches "Skip to content", which jumps past the sidebar.
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();

  // From there, Tab on to the sim button (past the 3D camera buttons) and press it.
  const sim = page.getByRole("button", { name: "Sim week 1" });
  for (let i = 0; i < 20 && !(await sim.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(sim).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Franchise overview" }).getByRole("status"))
    .toHaveText(/^Week 1: /);
  await context.close();
});
