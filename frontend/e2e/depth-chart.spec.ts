import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./support/fixtures";

const rows = (page: Page) => page.getByTestId("depth-row");

/** Drag like a person: press, move in small steps, release over the target. */
async function drag(page: Page, from: Locator, to: Locator) {
  const a = (await from.boundingBox())!;
  const b = (await to.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2, b.y + b.height / 2 - 4, { steps: 20 });
  await page.mouse.up();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/depth-chart");
  await expect(page.getByRole("heading", { name: "Quarterback" })).toBeVisible();
  await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Keegan Quarles");
});

test("dragging the backup QB to the top makes him the starter", async ({ page }) => {
  await expect(page.getByTitle("Offense 79")).toBeVisible();

  await drag(page, page.getByRole("button", { name: "Drag to reorder Kobe Sterling" }),
    page.getByRole("button", { name: "Drag to reorder Keegan Quarles" }));

  await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Kobe Sterling");
  await expect(rows(page).first()).toContainText("Starter");
  await expect(page.getByTitle("Offense 77")).toBeVisible();

  // Saved on the server: survives a reload, then reset restores OVR order.
  await page.reload();
  await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Kobe Sterling");
  await page.getByRole("button", { name: "Reset to OVR order" }).click();
  await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Keegan Quarles");
  await expect(page.getByTitle("Offense 79")).toBeVisible();
});

test("reorders with the keyboard and announces moves by name", async ({ page }) => {
  // dnd-kit's live region: what a screen reader hears.
  const announcer = page.locator("[id^=DndLiveRegion]");
  await page.getByRole("button", { name: "Drag to reorder Carter Fonoti" }).focus();

  await page.keyboard.press("Space");
  await expect(announcer).toHaveText("Picked up Carter Fonoti at QB 3 of 3.");
  // dnd-kit's KeyboardSensor attaches its arrow-key listener on the next task after
  // pickup; a key pressed in the same instant (impossible for a person) is dropped.
  await page.waitForTimeout(50);
  await page.keyboard.press("ArrowUp");
  await expect(announcer).toHaveText("Carter Fonoti is over QB 2 of 3.");
  await page.keyboard.press("ArrowUp");
  await expect(announcer).toHaveText("Carter Fonoti is over QB 1 of 3.");
  await page.keyboard.press("Space");
  await expect(announcer).toHaveText("Carter Fonoti moved to QB 1 of 3.");

  await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Carter Fonoti");
});

test("cross-lists a cornerback at free safety", async ({ page }) => {
  await page.getByRole("tab", { name: "Defense" }).click();
  await page.getByRole("button", { name: /Free Safety/ }).click();
  const before = await rows(page).count();
  const picker = page.getByRole("combobox", { name: "Add a player to FS" });
  const corner = picker.locator("option", { hasText: "CB ·" }).first();
  const label = (await corner.textContent())!;
  await picker.selectOption({ label });

  await expect(rows(page)).toHaveCount(before + 1);
  await expect(rows(page).last()).toContainText("CB");
  await rows(page).last().getByRole("button", { name: /^Remove/ }).click();
  await expect(rows(page)).toHaveCount(before);
});
