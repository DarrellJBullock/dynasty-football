import type { Page } from "@playwright/test";
import { expect, test } from "./support/fixtures";

/** Wait until it's this coach's call (or the game waits on the other coach); which one. */
async function turn(page: Page): Promise<"call" | "wait"> {
  const main = page.getByRole("main");
  const call = main.getByRole("region", { name: "Your call" });
  const wait = main.getByRole("region", { name: "Waiting" });
  await expect(call.or(wait)).toBeVisible({ timeout: 15_000 });
  return (await call.isVisible()) ? "call" : "wait";
}

async function yourCall(page: Page) {
  await expect(page.getByRole("main").getByRole("region", { name: "Your call" })).toBeVisible({ timeout: 15_000 });
}

test("two managers play their game live: an offer, a yes, blind calls, and the AI finishes",
  async ({ page, browser }) => {
    test.slow();
    const mine = await (await page.request.get("/api/franchise")).json();
    const next = await (await page.request.get("/api/franchise/next-game")).json();
    const game = next.game;
    const opponent = game.home.id === mine.team.id ? game.away : game.home;

    // A friend joins and takes this week's opponent.
    const invite = await (await page.request.post(`/api/leagues/${mine.league.id}/invites`)).json();
    const context = await browser.newContext();
    const friend = await context.newPage();
    expect((await friend.request.post("/api/auth/signup",
      { data: { email: "casey@example.test", password: "casey-password" } })).ok()).toBe(true);
    expect((await friend.request.post("/api/invites/join",
      { data: { token: invite.token, team_id: opponent.id } })).ok()).toBe(true);
    await friend.request.put("/api/auth/profile", { data: { display_name: "Casey" } });

    // Play Game offers to play it live; the friend says yes.
    await page.goto("/coach");
    const main = page.getByRole("main");
    await main.getByLabel("Call clock").selectOption({ label: "No clock" });
    await main.getByRole("button", { name: "Offer to play it live" }).click();
    await expect(main.getByText(/Waiting for Casey to say yes/)).toBeVisible();

    await friend.goto(`/games/${game.id}/live`);
    const theirs = friend.getByRole("main");
    await expect(theirs.getByText(/wants to play this game live with you/)).toBeVisible();
    await theirs.getByRole("button", { name: "Play it live" }).click();

    // The kickoff is one coach's decision; the other waits (and the page updates by itself).
    const [a, b] = await Promise.all([turn(page), turn(friend)]);
    expect([a, b].sort()).toEqual(["call", "wait"]);

    // Until a snap is both coaches' call (a kickoff or a conversion is one coach's), whoever
    // has the call takes the AI's suggestion. (Seeds differ between runs: ask the game.)
    const state = async (coach: Page) =>
      (await (await coach.request.get(`/api/games/${game.id}/live`)).json()).situation;
    for (let i = 0; i < 6; i++) {
      const [ours, theirsNow] = await Promise.all([state(page), state(friend)]);
      if (ours && theirsNow) break;
      const coach = ours ? page : friend;
      await yourCall(coach);
      const before = JSON.stringify(await state(coach));
      await coach.getByRole("main").getByRole("button", { name: "Call it" }).click();
      await expect.poll(async () => JSON.stringify(await state(coach))).not.toBe(before);
    }

    // Each snap is both coaches' call, blind: ours first, then the snap waits on theirs.
    await yourCall(page);
    await yourCall(friend);
    const plays = (await (await page.request.get(`/api/games/${game.id}/live`)).json()).plays.length;
    await main.getByRole("button", { name: "Call it" }).click();
    await expect(main.getByRole("heading", { name: `Waiting on ${opponent.abbreviation}` })).toBeVisible();
    await theirs.getByRole("button", { name: "Call it" }).click();
    await expect.poll(async () =>
      (await (await page.request.get(`/api/games/${game.id}/live`)).json()).plays.length).toBeGreaterThan(plays);

    // Both hand the rest to the AI (each when it's their call): the game finishes.
    const handed = new Set<Page>();
    for (let i = 0; i < 6 && handed.size < 2; i++) {
      const [ours, theirsNow] = await Promise.all([state(page), state(friend)]);
      for (const [coach, situation] of [[page, ours], [friend, theirsNow]] as const) {
        if (!situation || handed.has(coach)) continue;
        await yourCall(coach);
        const ai = coach.getByRole("main").getByRole("group", { name: "Let the AI call" });
        await ai.getByRole("button", { name: "The rest of the game" }).click();
        await ai.getByRole("button", { name: "Confirm: the AI finishes the game" }).click();
        const done = coach.getByRole("main").getByRole("region", { name: "Waiting" })
          .or(coach.getByRole("main").getByRole("region", { name: "Final" }));
        await expect(done).toBeVisible();
        handed.add(coach);
        break;
      }
    }
    for (const coach of [page, friend]) {
      await expect(coach.getByRole("main").getByRole("region", { name: "Final" }))
        .toBeVisible({ timeout: 15_000 });
    }
    const box = await (await page.request.get(`/api/games/${game.id}`)).json();
    expect(box.game.status).toBe("final");
    await context.close();
  });
