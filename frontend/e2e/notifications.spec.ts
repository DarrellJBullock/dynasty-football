import { expect, test } from "./support/fixtures";

test("the inbox: a friend joins and makes an offer, the badge counts, and reading clears it", async ({ page, browser }) => {
  const mine = await (await page.request.get("/api/franchise")).json();
  const leagueId = mine.league.id;
  const invite = await (await page.request.post(`/api/leagues/${leagueId}/invites`)).json();

  // A friend joins and offers a trade (through the API: those flows have their own specs).
  const context = await browser.newContext();
  const friend = await context.newPage();
  expect((await friend.request.post("/api/auth/signup",
    { data: { email: "jules@example.test", password: "jules-password" } })).ok()).toBe(true);
  await friend.request.put("/api/auth/profile", { data: { display_name: "Jules" } });
  const preview = await (await friend.request.post("/api/invites/preview", { data: { token: invite.token } })).json();
  const theirTeam = preview.open_teams[0];
  expect((await friend.request.post("/api/invites/join",
    { data: { token: invite.token, team_id: theirTeam.id } })).ok()).toBe(true);
  const desk = await (await friend.request.get(`/api/leagues/${leagueId}/trades?partner_id=${mine.team.id}`)).json();
  const offer = await friend.request.post(`/api/leagues/${leagueId}/trade-offers`, { data: {
    proposal: { partner_id: mine.team.id, send_players: [desk.mine.players.at(-1).id],
      receive_players: [desk.theirs.players.at(-1).id] } } });
  expect(offer.ok(), await offer.text()).toBe(true);
  await context.close();

  // The commissioner's sidebar counts two, and the inbox has both.
  await page.goto("/");
  const inboxLink = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Inbox/ });
  await expect(inboxLink).toContainText("2");
  await inboxLink.click();
  const list = page.getByRole("main").getByRole("list", { name: "Notifications" });
  await expect(list.getByRole("listitem", { name: /^Unread: Jules joined/ })).toBeVisible();
  const trade = list.getByRole("listitem", { name: /^Unread: Jules \(.+\) offers a trade$/ });
  await expect(trade).toContainText("You get");

  // Opening the offer marks it read and goes to the trade desk.
  await trade.getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`/trades\\?partner=${theirTeam.id}$`));
  await expect(page.getByRole("main").getByRole("region", { name: "Trade offers" })).toContainText("Jules");
  await expect(inboxLink).toContainText("1");

  // Mark the rest read: the badge goes.
  await page.goto("/inbox");
  await page.getByRole("main").getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByRole("main").getByRole("region", { name: "All caught up" })).toBeVisible();
  await expect(inboxLink).toHaveText("Inbox");
});
