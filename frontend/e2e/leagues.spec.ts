import { expect, navigate, test } from "./support/fixtures";

test("creates a custom league, switches back, and deletes it", async ({ page }) => {
  await page.goto("/leagues");
  await page.getByRole("link", { name: "+ Create league" }).click();
  await expect(page.getByRole("heading", { name: "Create a league" })).toBeVisible();
  await expect(page.getByTestId("builder-team")).toHaveCount(32);

  await page.getByRole("combobox", { name: "Conferences" }).selectOption("1");
  await page.getByRole("combobox", { name: "Divisions per conference" }).selectOption("2");
  await page.getByRole("combobox", { name: "Teams per division" }).selectOption("3");
  await expect(page.getByTestId("team-total")).toHaveText("6 teams");
  await expect(page.getByTestId("builder-team")).toHaveCount(6);

  await page.getByRole("textbox", { name: "Name", exact: true }).fill("Harbor Coast League");
  await page.getByRole("textbox", { name: "Abbreviation", exact: true }).fill("HCL");
  await page.getByRole("textbox", { name: "City for Burlington Lumberjacks" }).fill("Port Avalon");
  await page.getByRole("textbox", { name: "Nickname for Port Avalon Lumberjacks" }).fill("Krakens");
  await page.getByRole("textbox", { name: "Abbreviation for Port Avalon Krakens" }).fill("PAV");
  await page.getByRole("radio", { name: "Play as Port Avalon Krakens" }).check();
  await expect(page.getByText("You: PAV")).toBeVisible();

  await page.getByRole("button", { name: "Create league" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { level: 1, name: "Krakens" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Active roster" })).toContainText("53/53");

  await navigate(page, "League");
  await expect(page.getByRole("heading", { level: 1, name: "Harbor Coast League" })).toBeVisible();

  await navigate(page, "My Leagues");
  await expect(page.getByRole("listitem", { name: "Krakens Dynasty" })).toContainText("Active");
  const original = page.getByRole("listitem", { name: "Ironclads Dynasty" });
  await original.getByRole("button", { name: "Switch to this franchise" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { level: 1, name: "Ironclads" })).toBeVisible();

  await navigate(page, "My Leagues");
  const custom = page.getByRole("listitem", { name: "Krakens Dynasty" });
  await custom.getByRole("button", { name: "Delete Harbor Coast League" }).click();
  await custom.getByRole("button", { name: "Delete league" }).click();
  await expect(custom).toHaveCount(0);
  await expect(page.getByRole("main").getByRole("listitem")).toHaveCount(1);
});

test("blocks creating a league with an odd number of teams", async ({ page }) => {
  await page.goto("/leagues/new");
  await page.getByRole("combobox", { name: "Conferences" }).selectOption("1");
  await page.getByRole("combobox", { name: "Divisions per conference" }).selectOption("3");
  await page.getByRole("combobox", { name: "Teams per division" }).selectOption("3");
  // Scoped to <main>: Next.js adds its own route announcer with role="alert".
  await expect(page.getByRole("main").getByRole("alert")).toContainText("even number");
  await expect(page.getByRole("button", { name: "Create league" })).toBeDisabled();
});

test("edits a team's identity from the League page", async ({ page }) => {
  await page.goto("/league");
  await page.getByRole("button", { name: "Edit Providence Anchors" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit team" });

  await dialog.getByRole("textbox", { name: "Abbreviation" }).fill("ALB");
  await dialog.getByRole("button", { name: "Save team" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("ALB is already used by the Albany Sentinels");

  await dialog.getByRole("textbox", { name: "Abbreviation" }).fill("PVD");
  await dialog.getByRole("textbox", { name: "Nickname" }).fill("Lighthouse Keepers");
  await dialog.getByRole("button", { name: "Save team" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Edit Providence Lighthouse Keepers" })).toBeVisible();
});
