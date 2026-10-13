import { backendScript, expect, test } from "./support/fixtures";

test("a great career goes into the Hall of Fame, and his team retires his number", async ({ page }) => {
  const franchise = await (await page.request.get("/api/franchise")).json();
  await page.request.post(`/api/seasons/${franchise.season.id}/simulate`, { data: { until: "next_week" } });

  // A career that took years in a test's time: our best passer, retired long enough ago,
  // with an MVP; then the year's vote.
  const out = backendScript(`
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Award, Franchise, League, Player, PlayerGameStats, Season
from app.services import legacy
with SessionLocal() as db:
    league = db.scalar(select(League).order_by(League.id))
    season = league.seasons[0]
    team = db.scalar(select(Franchise.team_id).where(Franchise.league_id == league.id))
    star = db.scalars(select(Player).join(PlayerGameStats).where(PlayerGameStats.team_id == team)
                      .order_by(PlayerGameStats.pass_yds.desc(), Player.id)).first()
    star.retired_year = season.year - 3
    db.add(Award(season_id=season.id, award="mvp", player_id=star.id, team_id=team, summary="-"))
    db.flush()
    legacy.rules.BAR = 0.0  # (one week of stats is the whole case)
    legacy.induct(db, league, season.year)
    db.commit()
    print(star.id, star.full_name, star.jersey_number)
`).trim().split(" ");
  const [id, number] = [out[0], out.at(-1)!];
  const name = out.slice(1, -1).join(" ");

  // He's in the Hall of Fame, his case beside him.
  await page.goto("/hall-of-fame");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Hall of Fame" })).toBeVisible();
  const legend = main.getByRole("listitem", { name });
  await expect(legend).toContainText("MVP");

  // His team (ours) decides about his number: retire it from the record book.
  await page.goto("/records");
  await expect(main.getByRole("heading", { level: 1, name: franchise.team.full_name })).toBeVisible();
  await expect(main.getByRole("list", { name: "Hall of Famers" })).toContainText(name);
  await main.getByRole("button", { name: `Retire #${number}` }).click();
  await expect(main.getByRole("status")).toContainText(`Number ${number} is retired`);
  await expect(main.getByRole("list", { name: "Retired numbers" })).toContainText(name);

  // His page says so.
  await page.goto(`/players/${id}`);
  const career = main.getByRole("region", { name: "Career" });
  await expect(career.getByRole("link", { name: /^Hall of Fame · \d+$/ })).toBeVisible();
  await expect(career).toContainText(`Number retired · ${franchise.team.nickname}`);
});
