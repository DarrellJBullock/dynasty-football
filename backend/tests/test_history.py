import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.awards import (
    AWARDS,
    Candidate,
    choose,
    defense_points,
    offense_points,
    summary,
)
from app.models import Award, Franchise, Game, League, Player, Season
from tests.conftest import rollover

# ---------- pure rules ----------


def _candidate(pid: int, position: str, stats: dict, wins: int = 8, rookie: bool = False,
               games: int = 17) -> Candidate:
    return Candidate(pid, position, games, stats, wins, rookie)


def test_scoring():
    qb = {"pass_yds": 4000, "pass_td": 30, "pass_int": 10}
    assert offense_points(qb) == 4000 / 25 + 120 - 20
    assert defense_points({"tackles": 60, "sacks": 12, "interceptions": 1}) == 60 + 48 + 5


def test_choosing_winners():
    qb_winner = _candidate(1, "QB", {"pass_yds": 4200, "pass_td": 30}, wins=14)
    qb_loser = _candidate(2, "QB", {"pass_yds": 4400, "pass_td": 32}, wins=3)
    back = _candidate(3, "RB", {"rush_yds": 1900, "rush_td": 18}, rookie=True)
    edge = _candidate(4, "DE", {"tackles": 50, "sacks": 17})
    rookie_lb = _candidate(5, "MLB", {"tackles": 110, "sacks": 2}, rookie=True)
    hurt = _candidate(6, "WR", {"rec_yds": 1500, "rec_td": 14}, games=5)  # too few games
    winners = choose([qb_winner, qb_loser, back, edge, rookie_lb, hurt], weeks=17)
    assert winners["mvp"].player_id == 1  # the winner's QB edges a bigger season on a loser
    assert winners["opoy"].player_id == 2
    assert winners["oroy"].player_id == 3
    assert winners["dpoy"].player_id == 4
    assert winners["droy"].player_id == 5
    assert set(winners) == set(AWARDS)
    assert "droy" not in choose([qb_winner, edge], weeks=17)


@pytest.mark.parametrize("position, stats, text", [
    ("QB", {"pass_yds": 4512, "pass_td": 33, "pass_int": 9}, "4,512 pass yds · 33 TD · 9 INT"),
    ("RB", {"rush_yds": 1420, "rush_td": 11, "rec_td": 2}, "1,420 rush yds · 13 TD"),
    ("WR", {"receptions": 101, "rec_yds": 1390, "rec_td": 9}, "101 rec · 1,390 yds · 9 TD"),
    ("CB", {"tackles": 58, "sacks": 0, "interceptions": 7}, "58 tackles · 0 sacks · 7 INT"),
])
def test_summaries(position, stats, text):
    assert summary(position, stats) == text


# ---------- a finished season ----------


@pytest.fixture
def finished(client: TestClient, league: League) -> Season:
    season = league.seasons[0]
    sim = f"/api/seasons/{season.id}/simulate"
    client.post(sim, json={"until": "end_of_regular_season"})
    client.post(sim, json={"until": "end_of_playoffs"})
    return season


def test_awards_are_decided_with_the_champion(client: TestClient, db: Session,
                                              finished: Season, league: League):
    awards = db.scalars(select(Award).where(Award.season_id == finished.id)).all()
    assert {a.award for a in awards} == set(AWARDS)
    by_award = {a.award: a for a in awards}
    assert by_award["mvp"].player.position in ("QB", "RB", "WR", "TE", "FB")
    assert by_award["dpoy"].player.position in ("DE", "DT", "OLB", "MLB", "CB", "FS", "SS")
    # Everyone is a rookie in a league's first season.
    assert by_award["oroy"].summary and by_award["droy"].summary

    history = client.get(f"/api/leagues/{league.id}/history").json()
    season = history["seasons"][0]
    assert season["complete"] and season["champion"]["id"] == finished.champion_team_id
    final = db.scalar(select(Game).where(Game.season_id == finished.id, Game.stage == "playoff")
                      .order_by(Game.playoff_round.desc()).limit(1))
    assert {season["champion"]["id"], season["runner_up"]["id"]} == \
        {final.home_team_id, final.away_team_id}
    assert [a["award"] for a in season["awards"]] == list(AWARDS)
    assert season["franchise_record"]["wins"] + season["franchise_record"]["losses"] + \
        season["franchise_record"]["ties"] == 17
    assert season["franchise_result"] in {"Won the championship", "Missed the playoffs"} or \
        season["franchise_result"].startswith("Lost in the ")


def test_awards_are_decided_once_and_backfilled(client: TestClient, db: Session,
                                                finished: Season, league: League):
    first = {a.award: a.player_id for a in db.scalars(select(Award))}
    db.execute(delete(Award))
    db.commit()
    client.get(f"/api/leagues/{league.id}/history")
    assert {a.award: a.player_id for a in db.scalars(select(Award))} == first
    client.get(f"/api/leagues/{league.id}/history")
    assert len(db.scalars(select(Award)).all()) == len(AWARDS)


def test_records_match_the_season_leaders(client: TestClient, finished: Season, league: League):
    records = {c["key"]: c for c in client.get(f"/api/leagues/{league.id}/history")
               .json()["records"]}
    leaders = client.get(f"/api/leagues/{league.id}/leaders",
                         params={"category": "passing_yards", "limit": 5}).json()
    top = leaders["categories"][0]["leaders"][0]
    single = records["passing_yards"]["single_season"]
    assert (single[0]["player_id"], single[0]["value"]) == (top["player_id"], top["value"])
    assert single[0]["year"] == finished.year
    # One season played: career leaders are the season leaders.
    assert [(r["player_id"], r["value"]) for r in records["passing_yards"]["career"]] == \
        [(r["player_id"], r["value"]) for r in single]
    assert all(len(c["single_season"]) == 5 for c in records.values())


def test_career_page(client: TestClient, db: Session, finished: Season):
    mvp = db.scalar(select(Award).where(Award.season_id == finished.id, Award.award == "mvp"))
    career = client.get(f"/api/players/{mvp.player_id}/career").json()
    season_stats = client.get(f"/api/players/{mvp.player_id}/stats").json()
    assert [s["year"] for s in career["seasons"]] == [finished.year]
    assert career["games"] == season_stats["games"]
    for key, value in season_stats["totals"].items():
        if not key.endswith("_long"):
            assert career["totals"][key] == value
    assert [a["award"] for a in career["awards"]][0] in ("mvp", "opoy", "oroy")
    assert "mvp" in [a["award"] for a in career["awards"]]


def test_careers_and_rookies_span_seasons(client: TestClient, db: Session, finished: Season,
                                          league: League, franchise: Franchise):
    new_season = rollover(db, finished)
    db.commit()
    client.post(f"/api/seasons/{new_season.id}/simulate", json={"until": "next_week"})
    veteran = db.scalar(select(Award).where(Award.season_id == finished.id,
                                            Award.award == "opoy")).player
    career = client.get(f"/api/players/{veteran.id}/career").json()
    if veteran.team_id is not None and veteran.retired_year is None:
        assert [s["year"] for s in career["seasons"]][0] == finished.year
    history = client.get(f"/api/leagues/{league.id}/history").json()
    assert [s["year"] for s in history["seasons"]] == [new_season.year, finished.year]
    current = history["seasons"][0]
    assert not current["complete"] and current["awards"] == []
    assert current["franchise_result"] == "Season in progress"

    # Rookies are first-year pros: this year's draft class, never last year's players.
    from app.services.history import _rookies
    players = list(db.scalars(select(Player).where(Player.team_id.is_not(None))))
    rookies = _rookies(db, new_season, [p.id for p in players])
    drafted = {p.id for p in players if p.draft_year == new_season.year}
    assert rookies == drafted
    # Looking back, last season's rookies were the players then in their first year.
    from app.services.history import season_lines
    played = list(season_lines(db, finished))
    first_year = _rookies(db, finished, played)
    assert first_year and not first_year & drafted
    assert all(db.get(Player, pid).years_pro == 1 for pid in first_year
               if db.get(Player, pid).retired_year is None)
