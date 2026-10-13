import { expect, test } from "./support/fixtures";

test("two managers check in for the week, and the commissioner advances it", async ({ page, browser }) => {
  const mine = await (await page.request.get("/api/franchise")).json();
  const leagueId = mine.league.id;
  const invite = await (await page.request.post(`/api/leagues/${leagueId}/invites`)).json();

  // A friend joins (through the API: the invite flow has its own spec) and takes a team.
  const context = await browser.newContext();
  const friend = await context.newPage();
  expect((await friend.request.post("/api/auth/signup",
    { data: { email: "casey@example.test", password: "casey-password" } })).ok()).toBe(true);
  const preview = await (await friend.request.post("/api/invites/preview", { data: { token: invite.token } })).json();
  const joined = await friend.request.post("/api/invites/join",
    { data: { token: invite.token, team_id: preview.open_teams[0].id } });
  expect(joined.ok(), await joined.text()).toBe(true);

  // The friend, a manager: no sim buttons, but a check-in for week 1.
  await friend.goto("/");
  const theirs = friend.getByRole("main").getByRole("region", { name: "This step" });
  await expect(theirs.getByRole("heading", { name: "Next: Week 1" })).toBeVisible();
  await expect(friend.getByRole("main").getByText("The commissioner advances the season.")).toBeVisible();
  await expect(theirs.getByRole("button", { name: /^Advance/ })).toHaveCount(0);
  await theirs.getByRole("button", { name: "I'm ready" }).click();
  await expect(theirs.getByRole("button", { name: "Ready ✓" })).toBeVisible();
  await expect(theirs).toContainText("1 of 2 ready");

  // The commissioner sees it, checks in too, and advances.
  await page.goto("/");
  const panel = page.getByRole("main").getByRole("region", { name: "This step" });
  await expect(panel.getByRole("list", { name: "Managers" })).toContainText("casey: ready");
  await panel.getByRole("button", { name: "I'm ready" }).click();
  await expect(panel).toContainText("Everyone's ready");
  await panel.getByRole("button", { name: "Advance: Week 1" }).click();
  await expect(panel.getByRole("heading", { name: "Next: Week 2" })).toBeVisible();
  await expect(panel).toContainText("0 of 2 ready");

  // The friend's dashboard moves on with it.
  await friend.reload();
  await expect(theirs.getByRole("heading", { name: "Next: Week 2" })).toBeVisible();
  await expect(theirs.getByRole("button", { name: "I'm ready" })).toBeVisible();
  await context.close();
});
