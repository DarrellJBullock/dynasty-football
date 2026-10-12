import { expect, test } from "./support/fixtures";

test("a commissioner invites a friend, who signs up, picks a team and joins", async ({ page, browser }) => {
  const mine = await (await page.request.get("/api/franchise")).json();

  // The commissioner makes an invite link on the Members page.
  await page.goto("/members");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
  await main.getByRole("button", { name: "New invite link" }).click();
  const link = await main.getByLabel("Invite link (shown once)").inputValue();
  expect(link).toMatch(/\/join\?token=/);
  await expect(main.getByRole("list", { name: "Open invite links" })).toContainText("used 0 times");

  // A friend, in another browser, opens it: signs up first, then comes back to it.
  const context = await browser.newContext();
  const friend = await context.newPage();
  await friend.goto(link);
  await expect(friend).toHaveURL(/\/signin\?next=/);
  await friend.getByRole("link", { name: "Create an account" }).click();
  const signUp = friend.getByRole("form", { name: "Create an account" });
  await signUp.getByLabel("Email").fill("robin@example.test");
  await signUp.getByLabel("Password").fill("robin-password");
  await signUp.getByRole("button", { name: "Create account" }).click();
  await expect(friend).toHaveURL(/\/join\?token=/);
  await expect(friend.getByRole("heading", { name: `Join ${mine.league.name}` })).toBeVisible();

  // The commissioner's team isn't open; the friend takes another and lands on its dashboard.
  const teams = friend.getByRole("group", { name: "Open teams" });
  await expect(teams.getByRole("radio", { name: new RegExp(mine.team.full_name) })).toHaveCount(0);
  const pick = teams.getByRole("radio").first();
  const picked = (await pick.locator("xpath=..").innerText()).split("\n")[0].trim();
  await pick.check();
  await friend.getByRole("button", { name: "Join the league" }).click();
  await expect(friend).toHaveURL(/\/$/);
  const theirs = await (await friend.request.get("/api/franchise")).json();
  expect(theirs.team.id).not.toBe(mine.team.id);
  expect(theirs.role).toBe("manager");

  // The friend sets a display name; the commissioner sees it, not the email.
  await friend.goto("/account");
  const name = friend.getByRole("form", { name: "Display name" });
  await name.getByLabel("Name other members see").fill("Robin");
  await name.getByRole("button", { name: "Save name" }).click();
  await expect(name.getByRole("status")).toHaveText("Name saved.");

  // A manager can't change the commissioner's team.
  const refused = await friend.request.delete(`/api/teams/${mine.team.id}/depth-chart`);
  expect(refused.status()).toBe(403);
  await context.close();

  await page.reload();
  const robin = main.getByRole("listitem", { name: "Robin" });
  await expect(robin).toContainText(`Manager · ${theirs.team.full_name}`);
  await expect(main).not.toContainText("robin@example.test");
  await expect(main.getByRole("region", { name: "Open teams" })).not.toContainText(picked);
});
