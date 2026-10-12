import { existsSync } from "node:fs";
import path from "node:path";
import { expect, test } from "./support/fixtures";

// The Unity viewer runs only when its WebGL build is in public/unity/ (make unity-build,
// or CI's Unity job); without it there's nothing to load.
const BUILD = path.join(__dirname, "../public/unity/build.json");

test.describe("the Unity viewer", () => {
  test.skip(!existsSync(BUILD), "The Unity viewer isn't built (make unity-build).");

  test("plays a game's plays in Unity, remembered, with the page's controls", async ({ page }) => {
    test.slow(); // the WebGL build downloads and starts, and renders in software on CI
    await page.goto("/");
    const overview = page.getByRole("region", { name: "Franchise overview" });
    await overview.getByRole("button", { name: "Sim week 1" }).click();
    const result = overview.getByRole("status");
    await expect(result).toHaveText(/^Week 1: /);
    await result.click();
    await expect(page).toHaveURL(/\/games\/\d+$/);
    const watchUrl = `${page.url()}/watch?play=2`;
    await page.goto(watchUrl);

    const viewer = page.getByRole("region", { name: "Play viewer" });
    const renderer = viewer.getByRole("group", { name: "Renderer" });
    await renderer.getByRole("button", { name: "Unity" }).click();
    await expect(renderer.getByRole("button", { name: "Unity" })).toHaveAttribute("aria-pressed", "true");
    const unity = viewer.locator("[data-renderer=unity]");
    await expect(unity).toHaveAttribute("data-unity-state", "ready", { timeout: 60_000 });
    await expect(unity).toHaveAttribute("data-unity-plays", "1");

    // The page's clock drives it: the playhead moves, and the next play loads in Unity.
    const scrubber = viewer.getByRole("slider", { name: "Play timeline" });
    await expect.poll(async () => Number(await scrubber.inputValue()), { timeout: 20_000 }).toBeGreaterThan(0.3);
    await viewer.getByRole("button", { name: "Next play ›" }).click();
    await expect(unity).toHaveAttribute("data-unity-plays", "2");
    await expect(viewer.getByRole("alert")).toHaveCount(0); // no fallback

    // The choice is remembered; Classic is one click away.
    await page.reload();
    await expect(viewer.locator("[data-renderer=unity]")).toBeVisible();
    await renderer.getByRole("button", { name: "Classic" }).click();
    await expect(viewer.locator("[data-renderer=unity]")).toHaveCount(0);
    await expect(viewer.getByRole("img", { name: "3D play" })).toBeVisible();
  });
});
