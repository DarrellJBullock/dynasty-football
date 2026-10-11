import { expect, navigate, test } from "./support/fixtures";

test("dashboard shows the sample franchise", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Ironclads" })).toBeVisible();
  await expect(page.getByText("Ironclads Dynasty · 2026 Preseason")).toBeVisible();
  await expect(page.getByTitle("79 overall (good)").first()).toBeVisible();
  const nextGame = page.getByRole("region", { name: "Next game" });
  await expect(nextGame.getByText("Albuquerque Roadrunners")).toBeVisible();
  await expect(page.getByRole("region", { name: "Front office" })).toContainText("contract(s) expire");
  // The 3D preview mounts a WebGL canvas.
  await expect(page.getByRole("region", { name: "Franchise overview" }).locator("canvas")).toBeVisible();
});

test("sidebar reaches every page", async ({ page }) => {
  await page.goto("/");
  const pages: [string, RegExp | string][] = [
    ["Roster", "Hartford Ironclads"],
    ["Depth Chart", "Hartford Ironclads"],
    ["Contracts", "Contracts"],
    ["Free Agency", "Free Agency"],
    ["Draft", /^\d{4} Draft$/],
    ["League", "Dynasty Football League"],
    ["My Leagues", "Leagues & franchises"],
    ["Dashboard", "Ironclads"],
  ];
  for (const [link, heading] of pages) {
    await navigate(page, link);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: link, exact: true }))
      .toHaveAttribute("aria-current", "page");
  }
});
