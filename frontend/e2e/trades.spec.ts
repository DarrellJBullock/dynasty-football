import { expect, navigate, test } from "./support/fixtures";

test("trades a player for a player and sees it on the roster", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "Trades");
  await expect(page.getByRole("heading", { level: 1, name: "Trades" })).toBeVisible();

  // My most valuable player for their least valuable one: they'll say yes.
  const mine = page.getByRole("region", { name: /\(you\) assets$/ });
  const theirs = page.getByRole("region", { name: /assets$/ }).last();
  // Players are listed most valuable first (picks sit above, in their own list).
  const myStar = mine.getByRole("table").getByRole("checkbox").first();
  const theirBackup = theirs.getByRole("table").getByRole("checkbox").last();
  const incoming = (await theirBackup.getAttribute("aria-label"))!.replace(/^Trade /, "");
  await myStar.check();
  await theirBackup.check();

  const deal = page.getByRole("region", { name: "Deal" });
  await expect(deal.getByRole("status", { name: "Their answer" })).toContainText("would accept");
  await deal.getByRole("button", { name: "Propose trade" }).click();
  await expect(deal.getByRole("status", { name: "Trade result" })).toContainText("Trade done");
  await expect(page.getByRole("region", { name: "Trade history" })).toContainText(incoming);

  await navigate(page, "Roster");
  await expect(page.getByRole("main").getByText(incoming, { exact: true })).toBeVisible();
});

test("a lopsided offer is turned down", async ({ page }) => {
  await page.goto("/trades");
  const mine = page.getByRole("region", { name: /\(you\) assets$/ });
  const theirs = page.getByRole("region", { name: /assets$/ }).last();
  await mine.getByRole("table").getByRole("checkbox").last().check();
  await theirs.getByRole("table").getByRole("checkbox").first().check(); // their best player
  const deal = page.getByRole("region", { name: "Deal" });
  await expect(deal.getByRole("status", { name: "Their answer" })).toContainText("want more");
  await expect(deal.getByRole("meter", { name: "Trade meter" })).toBeVisible();
});
