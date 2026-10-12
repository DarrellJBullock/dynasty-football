import { expect, test } from "./support/fixtures";

// Sound (docs/design/sound.md) can't be heard in a test, but the engine reports what it's
// doing on window.dynastySound: the audio context's state and the last sounds played.
test("turns the game's sound on, plays the play's sounds, and remembers it", async ({ page }) => {
  test.slow(); // 3D on CI renders in software
  await page.goto("/");
  const overview = page.getByRole("region", { name: "Franchise overview" });
  await overview.getByRole("button", { name: "Sim week 1" }).click();
  const result = overview.getByRole("status");
  await expect(result).toHaveText(/^Week 1: /);
  await result.click();
  await expect(page).toHaveURL(/\/games\/\d+$/);
  await page.goto(`${page.url()}/watch?play=2`);

  const viewer = page.getByRole("region", { name: "Play viewer" });
  const sound = viewer.getByRole("group", { name: "Sound" });
  await sound.getByRole("button", { name: "Sound off" }).click();
  await expect(sound.getByRole("button", { name: "Sound on" })).toHaveAttribute("aria-pressed", "true");
  await expect(sound.getByRole("slider", { name: "Volume" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.dynastySound?.state)).toBe("running");

  // Play it from the start: the snap count, the snap and the whistle sound in turn.
  const scrubber = viewer.getByRole("slider", { name: "Play timeline" });
  await viewer.getByRole("button", { name: /^(Pause|Play|Replay)$/ }).first().click();
  await scrubber.fill("0");
  const play = viewer.getByRole("button", { name: "Play", exact: true });
  if (await play.isVisible()) await play.click();
  await expect.poll(() => page.evaluate(() => window.dynastySound?.played ?? []), { timeout: 20_000 })
    .toEqual(expect.arrayContaining(["cadence", "snap", "whistle"]));

  // Remembered: on after a reload (the browser starts it again on the next interaction).
  await page.reload();
  await expect(viewer.getByRole("group", { name: "Sound" }).getByRole("button", { name: "Sound on" }))
    .toHaveAttribute("aria-pressed", "true");
  await viewer.getByRole("group", { name: "Sound" }).getByRole("checkbox", { name: "Crowd" }).click();
  await expect.poll(() => page.evaluate(() => window.dynastySound?.state)).toBe("running");
});
