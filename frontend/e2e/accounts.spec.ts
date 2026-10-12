import { E2E_USER } from "./support/env";
import { expect, test } from "./support/fixtures";

test("signs out, signs up a second account that can't see the first one's league, and signs back in", async ({ page }) => {
  // The first account's league: one of its games.
  const franchise = await (await page.request.get("/api/franchise")).json();
  const schedule = await (await page.request.get(`/api/leagues/${franchise.league.id}/schedule`)).json();
  const gameId = schedule.games[0].id;

  await page.goto("/");
  const account = page.getByRole("group", { name: "Account" });
  await expect(account.getByRole("link", { name: E2E_USER.email })).toBeVisible();
  await account.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/signin$/);

  // Signed out, every page leads to signing in.
  await page.goto("/roster");
  await expect(page).toHaveURL(/\/signin\?next=%2Froster$/);

  // A new account starts by building its league, and can't reach the first one's games.
  await page.getByRole("link", { name: "Create an account" }).click();
  const signUp = page.getByRole("form", { name: "Create an account" });
  await signUp.getByLabel("Email").fill("rival@example.test");
  await signUp.getByLabel("Password").fill("rival-password");
  await signUp.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/leagues\/new$/);
  await expect(page.getByRole("group", { name: "Account" })).toContainText("rival@example.test");
  await page.goto(`/games/${gameId}`);
  await expect(page.getByRole("main")).toContainText("Not found.");
  await page.goto("/");
  await expect(page.getByRole("main").getByRole("link", { name: "Build your league" })).toBeVisible();

  // Back to the first account, and on to where it was headed.
  await page.getByRole("group", { name: "Account" }).getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/signin$/);
  await page.goto("/roster");
  const signIn = page.getByRole("form", { name: "Sign in" });
  await signIn.getByLabel("Email").fill(E2E_USER.email);
  await signIn.getByLabel("Password").fill("not-the-password");
  await signIn.getByRole("button", { name: "Sign in" }).click();
  await expect(signIn.getByRole("alert")).toHaveText("Wrong email or password.");
  await signIn.getByLabel("Password").fill(E2E_USER.password);
  await signIn.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/roster$/);
  await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toBeVisible();
});
