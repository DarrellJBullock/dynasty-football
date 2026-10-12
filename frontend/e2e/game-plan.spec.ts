import { expect, navigate, test } from "./support/fixtures";

test("edits and saves the franchise's game plan", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "Game Plan");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Game plan" })).toBeVisible();
  await expect(main.getByText("Suggested for your roster", { exact: true })).toBeVisible();

  await main.getByRole("checkbox", { name: /^Toss/ }).uncheck();
  await main.getByRole("group", { name: "Run or pass" }).getByText("Much more").click();
  await main.getByRole("button", { name: "Save game plan" }).click();
  await expect(main.getByRole("status")).toHaveText("Game plan saved.");

  await page.reload();
  await expect(main.getByText("Your plan", { exact: true })).toBeVisible();
  await expect(main.getByRole("checkbox", { name: /^Toss/ })).not.toBeChecked();
  await expect(main.getByRole("group", { name: "Run or pass" }).getByRole("radio", { name: "Much more" }))
    .toBeChecked();
});
