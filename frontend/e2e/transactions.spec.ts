import { expect, navigate, test } from "./support/fixtures";

test("every trade in the league is on the Transactions page", async ({ page }) => {
  const mine = await (await page.request.get("/api/franchise")).json();
  const leagueId = mine.league.id;
  // A trade with an AI team (through the API: trading has its own spec).
  const desk = await (await page.request.get(`/api/leagues/${leagueId}/trades`)).json();
  const ours = desk.mine.players[0];
  const result = await (await page.request.post(`/api/leagues/${leagueId}/trades`, { data: {
    partner_id: desk.partner.id, send_players: [ours.id],
    receive_players: [desk.theirs.players.at(-1).id] } })).json();
  expect(result.accepted).toBe(true);

  await page.goto("/");
  await navigate(page, "Transactions");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Transactions" })).toBeVisible();
  const trades = main.getByRole("list", { name: "Trades" });
  await expect(trades.getByRole("listitem").first()).toContainText("A manager and the AI");
  await expect(trades.getByRole("listitem").first()).toContainText(ours.label);
});
