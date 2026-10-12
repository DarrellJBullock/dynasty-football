import { expect, navigate, test } from "./support/fixtures";

test("audibles at the line in Coach Mode, from the game plan", async ({ page }) => {
  test.slow();
  // Audibles on both sides of the ball, so whichever we have first stops at the line.
  const franchise = await (await page.request.get("/api/franchise")).json();
  const url = `/api/teams/${franchise.team.id}/game-plan`;
  const plan = await (await page.request.get(url)).json();
  const saved = await page.request.put(url, { data: {
    offense: plan.offense, defense: plan.defense, tendencies: plan.tendencies,
    offense_audibles: ["slants", "inside_zone"], defense_audibles: ["cover0", "cover2"] } });
  expect(saved.ok()).toBe(true);

  await page.goto("/");
  await navigate(page, "Play Game");
  await page.getByRole("button", { name: "Start coaching" }).click();
  const call = page.getByRole("region", { name: "Your call" });
  const atTheLine = call.getByRole("heading", { name: "At the line" });
  const log = page.getByRole("complementary", { name: "Play-by-play" }).getByRole("listitem");

  // Take the AI's calls until the first stop at the line (each call either plays a snap or,
  // for a play, stops at the line first).
  const callIt = call.getByRole("button", { name: "Call it" });
  await expect(callIt.or(atTheLine).first()).toBeVisible();
  for (let i = 0; i < 6 && !(await atTheLine.isVisible()); i++) {
    const plays = await log.count();
    await callIt.click();
    await expect.poll(async () => (await atTheLine.isVisible()) || (await log.count()) > plays)
      .toBe(true);
    await expect(callIt.or(atTheLine).first()).toBeEnabled();
  }
  await expect(atTheLine).toBeVisible();
  await expect(call.getByTestId("look")).toHaveText(/^The (defense shows \w+ personnel|offense lines up in )/);

  const before = await log.count();
  const audibles = call.getByRole("group", { name: "Audibles" });
  await audibles.getByRole("button", { name: /^Audible: / }).first().click();
  await expect.poll(() => log.count()).toBeGreaterThan(before);
  await expect(atTheLine).toBeHidden();
});
