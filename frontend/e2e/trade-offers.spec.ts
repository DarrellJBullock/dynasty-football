import { expect, test } from "./support/fixtures";

test("two managers trade: an offer, a counter-offer, and a yes", async ({ page, browser }) => {
  const mine = await (await page.request.get("/api/franchise")).json();
  const leagueId = mine.league.id;
  const invite = await (await page.request.post(`/api/leagues/${leagueId}/invites`)).json();

  // A friend joins (through the API: the invite flow has its own spec) and takes a team.
  const context = await browser.newContext();
  const friend = await context.newPage();
  expect((await friend.request.post("/api/auth/signup",
    { data: { email: "drew@example.test", password: "drew-password" } })).ok()).toBe(true);
  const preview = await (await friend.request.post("/api/invites/preview", { data: { token: invite.token } })).json();
  const theirTeam = preview.open_teams[0];
  expect((await friend.request.post("/api/invites/join",
    { data: { token: invite.token, team_id: theirTeam.id } })).ok()).toBe(true);
  await friend.request.put("/api/auth/profile", { data: { display_name: "Drew" } });

  // Backups, one for one (rosters are full): theirs and ours.
  const desk = await (await page.request.get(`/api/leagues/${leagueId}/trades?partner_id=${theirTeam.id}`)).json();
  const myBackup = desk.mine.players.at(-1).player.full_name;
  const theirBackup = desk.theirs.players.at(-1).player.full_name;
  const theirOther = desk.theirs.players.at(-2).player.full_name;

  // The commissioner offers a trade, with a note.
  await page.goto(`/trades?partner=${theirTeam.id}`);
  const main = page.getByRole("main");
  await main.getByLabel(`Trade ${myBackup}`).check();
  await main.getByLabel(`Trade ${theirBackup}`).check();
  await expect(main.getByRole("status", { name: "Their answer" })).toContainText("manager decides");
  await main.getByLabel("Note to Drew (optional)").fill("Backups for backups?");
  await main.getByRole("button", { name: "Send offer" }).click();
  await expect(main.getByRole("status", { name: "Trade result" })).toHaveText("Offer sent to Drew.");
  await expect(main.getByRole("region", { name: "Trade offers" })).toContainText("Waiting for an answer");

  // The friend counters: their other backup instead.
  await friend.goto("/trades");
  const theirs = friend.getByRole("main").getByRole("region", { name: "Trade offers" });
  await expect(theirs).toContainText("“Backups for backups?”");
  await theirs.getByRole("button", { name: "Counter…" }).click();
  const deal = friend.getByRole("main").getByRole("region", { name: "Deal" });
  await expect(deal.getByRole("group", { name: "You give" })).toContainText(theirBackup);
  await friend.getByRole("main").getByLabel(`Trade ${theirBackup}`).uncheck();
  await friend.getByRole("main").getByLabel(`Trade ${theirOther}`).check();
  await friend.getByRole("main").getByRole("button", { name: "Send counter-offer" }).click();
  await expect(theirs).toContainText("Countered");
  await context.close();

  // The commissioner accepts the counter: the players change teams.
  await page.goto("/trades");
  const offers = main.getByRole("region", { name: "Trade offers" });
  await offers.getByRole("button", { name: "Accept" }).click();
  await expect(offers.getByRole("status")).toContainText("done");
  await expect(main.getByRole("region", { name: "Trade history" })).toContainText(theirOther);
  const roster = await (await page.request.get(`/api/teams/${mine.team.id}/roster`)).json();
  expect(roster.map((p: { full_name: string }) => p.full_name)).toContain(theirOther);
});
