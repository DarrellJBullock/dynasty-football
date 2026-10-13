import { expect, navigate, test } from "./support/fixtures";

test("the League page shows where every front office is going, and why", async ({ page }) => {
  await page.goto("/");
  await navigate(page, "League");
  const offices = page.getByRole("main").getByRole("region", { name: "Front offices" });
  const franchise = await (await page.request.get("/api/franchise")).json();
  await expect(offices.getByRole("listitem").first())
    .toContainText(`${franchise.team.full_name}Run by`);
  const listed = await (await page.request.get(`/api/leagues/${franchise.league.id}/front-offices`)).json();
  const ai = listed.find((o: { direction: string | null }) => o.direction !== null);
  const row = offices.getByRole("group").filter({ hasText: ai.team.full_name });
  await row.getByText(ai.label).click();
  await expect(row).toContainText(ai.reasons[0]);
});
