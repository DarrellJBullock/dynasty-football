import { expect, navigate, test } from "./support/fixtures";

test("the commissioner edits a player, and every member sees it in the League log",
  async ({ page, browser }) => {
    const mine = await (await page.request.get("/api/franchise")).json();
    const roster = await (await page.request.get(`/api/teams/${mine.team.id}/roster`)).json();
    const player = roster.at(-1);

    // The commissioner rewrites a contract, then sends the player to free agency.
    await page.goto(`/players/${player.id}`);
    const tools = page.getByRole("main").getByRole("region", { name: "Commissioner" });
    await tools.getByLabel("Salary ($M a season)").fill("4");
    await tools.getByLabel("Years").selectOption("3");
    await tools.getByRole("button", { name: "Save contract" }).click();
    await expect(tools.getByRole("status")).toContainText("$4.0M a season");
    await tools.getByLabel("Move to").selectOption({ label: "Free agency" });
    await tools.getByRole("button", { name: "Move player" }).click();
    await expect(tools.getByRole("status")).toHaveText("Moved to free agency.");

    await navigate(page, "League Log");
    const entries = page.getByRole("main").getByRole("region", { name: "League log entries" });
    await expect(entries.getByRole("listitem").first())
      .toContainText(`Moved ${player.full_name} from ${mine.team.full_name} to free agency`);
    await expect(entries).toContainText(`Changed ${player.full_name}'s contract to $4.00M a season`);

    // A friend joins as a manager: they see the log, but can't edit players.
    const invite = await (await page.request.post(`/api/leagues/${mine.league.id}/invites`)).json();
    const context = await browser.newContext();
    const friend = await context.newPage();
    expect((await friend.request.post("/api/auth/signup",
      { data: { email: "jordan@example.test", password: "jordan-password" } })).ok()).toBe(true);
    const preview = await (await friend.request.post("/api/invites/preview", { data: { token: invite.token } })).json();
    expect((await friend.request.post("/api/invites/join",
      { data: { token: invite.token, team_id: preview.open_teams[0].id } })).ok()).toBe(true);

    await friend.goto("/league-log");
    await expect(friend.getByRole("main").getByRole("region", { name: "League log entries" }))
      .toContainText(`Moved ${player.full_name}`);
    await friend.goto("/roster");
    await expect(friend.getByRole("main").getByRole("heading", { level: 1 })).toBeVisible();
    await expect(friend.getByRole("main").getByRole("button", { name: "+ Create player" })).toHaveCount(0);
    await context.close();
  });
