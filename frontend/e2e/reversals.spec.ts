import { expect, navigate, test } from "./support/fixtures";

test("the commissioner reverses a trade, then rolls back a week", async ({ page }) => {
  test.slow();
  const mine = await (await page.request.get("/api/franchise")).json();
  const leagueId = mine.league.id;

  // A trade with an AI team (through the API: trading has its own spec).
  const desk = await (await page.request.get(`/api/leagues/${leagueId}/trades`)).json();
  const ours = desk.mine.players[0];
  const theirs = desk.theirs.players.at(-1);
  const result = await (await page.request.post(`/api/leagues/${leagueId}/trades`, { data: {
    partner_id: desk.partner.id, send_players: [ours.id], receive_players: [theirs.id] } })).json();
  expect(result.accepted).toBe(true);

  await page.goto("/");
  await navigate(page, "Trades");
  const trades = page.getByRole("main").getByRole("region", { name: "This season's trades" });
  await trades.getByRole("button", { name: /^Reverse the trade between/ }).first().click();
  await trades.getByRole("button", { name: "Confirm: reverse it" }).click();
  await expect(trades.getByRole("status")).toContainText("have everyone back");
  await expect(trades.getByText("Reversed", { exact: true })).toBeVisible();
  const back = await (await page.request.get(`/api/players/${ours.id}`)).json();
  expect(back.team_id).toBe(mine.team.id);

  // A week is played, then rolled back from the League log.
  expect((await page.request.post(`/api/seasons/${mine.season.id}/simulate`,
    { data: { until: "next_week" } })).ok()).toBe(true);
  await navigate(page, "League Log");
  const main = page.getByRole("main");
  const panel = main.getByRole("region", { name: "Roll back a week" });
  await panel.getByRole("button", { name: "Roll back Week 1" }).click();
  await panel.getByRole("button", { name: "Confirm: roll back Week 1" }).click();
  await expect(panel.getByRole("status")).toHaveText("Week 1 was rolled back: it will be played again.");
  const entries = main.getByRole("region", { name: "League log entries" });
  await expect(entries.getByRole("listitem").first()).toContainText("Rolled back Week 1");
  await expect(entries).toContainText("Reversed the trade between");

  const season = await (await page.request.get("/api/franchise")).json();
  expect(season.season.current_week).toBe(1);
  const week = await (await page.request.get(`/api/leagues/${leagueId}/schedule?week=1`)).json();
  expect(week.games.length).toBeGreaterThan(0);
  expect(week.games.every((g: { status: string }) => g.status === "scheduled")).toBe(true);
});
