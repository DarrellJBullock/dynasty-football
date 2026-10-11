import random
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import MIN_SALARY
from app.domain.draft import (
    ROOKIE_YEARS,
    ROUNDS,
    SCOUTING_REPORTS,
    Finish,
    class_size,
    draft_order,
    potential_grade,
    prospect_target,
    rookie_salary,
    scout_noise,
)
from app.domain.positions import ROSTER_MAX
from app.models import DraftPick, Franchise, League, Player, Season
from app.services import draft, free_agency
from app.services.offseason import advance

# ---------- pure rules ----------


def test_class_quality_falls_with_rank():
    rng = random.Random(1)
    size = class_size(32)
    top = [prospect_target(rng, r, size) for r in range(10)]
    bottom = [prospect_target(rng, r, size) for r in range(size - 10, size)]
    assert sum(o for o, _ in top) > sum(o for o, _ in bottom) + 100
    assert sum(u for _, u in top) > sum(u for _, u in bottom)
    assert all(u >= 2 for _, u in top + bottom)


def test_rookie_scale():
    assert rookie_salary(1, MIN_SALARY) == 10_000_000
    salaries = [rookie_salary(n, MIN_SALARY) for n in range(1, 120)]
    assert salaries == sorted(salaries, reverse=True)
    assert rookie_salary(101, MIN_SALARY) == MIN_SALARY


@pytest.mark.parametrize("potential, grade", [(90, "A+"), (80, "A"), (73, "B"), (60, "D")])
def test_potential_grades(potential, grade):
    assert potential_grade(potential) == grade


def test_draft_order_worst_first_champion_last():
    finishes = [Finish(1, 4, 0.8, 120),  # champion
                Finish(2, 3, 0.75, 90),  # runner-up
                Finish(3, 1, 0.6, 40),   # lost in the first round
                Finish(4, 0, 0.6, 30),   # missed the playoffs, 10-7
                Finish(5, 0, 0.2, -150),  # worst record
                Finish(6, 0, 0.6, 10)]   # 10-7, worse point differential than team 4
    assert draft_order(finishes, salt="x") == [5, 6, 4, 3, 2, 1]
    tie = [Finish(7, 0, 0.5, 0), Finish(8, 0, 0.5, 0)]
    assert draft_order(tie, salt="a") == draft_order(tie, salt="a")


def test_scouting_error_is_stable_per_prospect():
    assert scout_noise(1, "2027:A B:WR") == scout_noise(1, "2027:A B:WR") \
        != scout_noise(1, "2027:A C:WR")


# ---------- the class and scouting ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _draft_view(client: TestClient, league: League) -> dict:
    return client.get(f"/api/leagues/{league.id}/draft").json()


def test_next_class_is_generated_once_and_hidden(client: TestClient, db: Session,
                                                 league: League, season: Season,
                                                 franchise: Franchise):
    view = _draft_view(client, league)
    assert view["year"] == season.year + 1 and view["status"] == "upcoming"
    assert view["picks"] == [] and view["scouting_left"] == SCOUTING_REPORTS
    assert len(view["prospects"]) == class_size(32)
    row = view["prospects"][0]
    assert row["overall"] is None and row["potential"] is None and not row["scouted"]
    assert row["high"] - row["low"] == 8
    assert [p["id"] for p in _draft_view(client, league)["prospects"]] == \
        [p["id"] for p in view["prospects"]]  # generated once

    free_agents = {p["id"] for p in client.get(f"/api/leagues/{league.id}/free-agents").json()}
    assert row["id"] not in free_agents
    signing = client.post(f"/api/teams/{franchise.team_id}/signings",
                          json={"player_id": row["id"], "years": 1})
    assert signing.status_code == 409 and "draft class" in signing.json()["detail"]


def test_scouting_reveals_the_truth_within_a_budget(client: TestClient, db: Session,
                                                    league: League):
    prospects = _draft_view(client, league)["prospects"]
    report = client.post(f"/api/players/{prospects[0]['id']}/scout").json()
    player = db.get(Player, prospects[0]["id"])
    assert report["scouted"] and report["overall"] == player.overall == report["projected"]
    assert report["potential"] == player.potential and report["low"] == report["high"]
    assert _draft_view(client, league)["scouting_left"] == SCOUTING_REPORTS - 1
    # Scouting the same prospect again is free.
    client.post(f"/api/players/{prospects[0]['id']}/scout")
    assert _draft_view(client, league)["scouting_left"] == SCOUTING_REPORTS - 1

    for row in prospects[1:SCOUTING_REPORTS]:
        assert client.post(f"/api/players/{row['id']}/scout").status_code == 200
    over = client.post(f"/api/players/{prospects[SCOUTING_REPORTS]['id']}/scout")
    assert over.status_code == 409 and "No scouting reports left" in over.json()["detail"]
    veteran = db.scalars(select(Player).where(Player.team_id.is_not(None))).first()
    assert client.post(f"/api/players/{veteran.id}/scout").status_code == 409


# ---------- draft day ----------


@pytest.fixture
def live(db: Session, season: Season) -> Season:
    """The next season, with free agency played and the draft open."""
    season.phase = "offseason"
    new_season = advance(db, season)
    free_agency.play_days(db, new_season, "end")
    db.commit()  # (to the test's savepoint) so a rejected request's rollback keeps it
    return new_season


def _picks(db: Session, season: Season) -> list[DraftPick]:
    return db.scalars(select(DraftPick).where(DraftPick.season_id == season.id)
                      .order_by(DraftPick.number)).all()


def test_the_draft_opens_after_free_agency(client: TestClient, db: Session, live: Season,
                                           season: Season, league: League):
    assert live.phase == "draft"
    picks = _picks(db, live)
    assert len(picks) == ROUNDS * 32
    first_round = [p.team_id for p in picks[:32]]
    assert len(set(first_round)) == 32
    assert [p.team_id for p in picks[32:64]] == first_round  # same order every round
    assert first_round[-1] == season.champion_team_id or season.champion_team_id is None
    view = _draft_view(client, league)
    assert view["status"] == "live" and view["on_the_clock"] == 1 and view["year"] == live.year
    sim = client.post(f"/api/seasons/{live.id}/simulate", json={"until": "next_week"})
    assert sim.status_code == 409 and "draft" in sim.json()["detail"]


def test_franchise_picks_when_on_the_clock(client: TestClient, db: Session, live: Season,
                                           league: League, franchise: Franchise):
    view = _draft_view(client, league)
    target = view["prospects"][0]
    early = client.post(f"/api/leagues/{league.id}/draft/pick", json={"player_id": target["id"]})
    if view["my_next_pick"] != 1:
        assert early.status_code == 409 and "not on the clock" in early.json()["detail"]

    result = client.post(f"/api/seasons/{live.id}/draft", json={"until": "my_pick"}).json()
    view = _draft_view(client, league)
    assert view["on_the_clock"] == view["my_next_pick"]
    assert len(result["picks"]) == view["on_the_clock"] - 1
    available = view["prospects"][0]
    pick = client.post(f"/api/leagues/{league.id}/draft/pick",
                       json={"player_id": available["id"]}).json()["picks"][0]
    assert pick["player"]["id"] == available["id"] and pick["team"]["id"] == franchise.team_id

    player = db.get(Player, available["id"])
    assert player.team_id == franchise.team_id and not player.is_prospect
    assert (player.draft_year, player.draft_round, player.draft_pick) == \
        (live.year, pick["round"], pick["number"])
    contract = player.active_contract
    assert contract.salary == rookie_salary(pick["number"], MIN_SALARY)
    assert (contract.years, contract.start_year) == (ROOKIE_YEARS, live.year)
    taken = client.post(f"/api/leagues/{league.id}/draft/pick",
                        json={"player_id": available["id"]})
    assert taken.status_code == 409


def test_finishing_the_draft(client: TestClient, db: Session, live: Season, league: League,
                             franchise: Franchise):
    result = client.post(f"/api/seasons/{live.id}/draft", json={"until": "end"}).json()
    assert result["season"]["phase"] == "preseason"
    assert all(p.player_id for p in _picks(db, live))
    view = _draft_view(client, league)  # the finished draft stays up until the season
    assert (view["status"], view["year"], len(view["picks"])) == ("complete", live.year, 224)
    log = live.offseason_log
    assert len(log["drafted"]) == ROUNDS * 32

    teams = {t["id"]: t for t in client.get(f"/api/leagues/{league.id}/teams").json()}
    for team_id, team in teams.items():
        if team_id != franchise.team_id:
            assert team["roster_count"] == ROSTER_MAX and team["cap_space"] >= 0
    leftovers = db.scalars(select(Player).where(Player.draft_year == live.year,
                                                Player.team_id.is_(None))).all()
    assert leftovers and not any(p.is_prospect for p in leftovers)  # free agents now

    # AI teams draft by value: early picks are better prospects than late ones.
    players = {p.id: p for p in db.scalars(select(Player).where(Player.draft_year == live.year))}
    value = [players[e["player"]].overall + players[e["player"]].potential
             for e in log["drafted"]]
    assert sum(value[:32]) > sum(value[-32:]) + 32 * 10

    # The franchise must be at 53 before week 1.
    roster = teams[franchise.team_id]["roster_count"]
    sim = client.post(f"/api/seasons/{live.id}/simulate", json={"until": "next_week"})
    if roster > ROSTER_MAX:
        assert sim.status_code == 409 and "Cut your roster" in sim.json()["detail"]
        dashboard = client.get("/api/franchise/dashboard").json()
        assert any("Cut your roster" in a["message"] for a in dashboard["alerts"])
        cut = client.post(f"/api/teams/{franchise.team_id}/cut-down").json()
        assert len(cut) == roster - ROSTER_MAX
        sim = client.post(f"/api/seasons/{live.id}/simulate", json={"until": "next_week"})
    assert sim.status_code == 200


def test_draft_is_deterministic(db: Session, league: League):
    def run() -> list[tuple]:
        season = league.seasons[0]
        season.phase = "offseason"
        new_season = advance(db, season)
        free_agency.play_days(db, new_season, "end")
        draft.play(db, new_season, "end")
        return [(e["team"], db.get(Player, e["player"]).full_name, e["pick"])
                for e in new_season.offseason_log["drafted"]]

    savepoint = db.begin_nested()
    first = run()
    savepoint.rollback()
    db.expire_all()
    assert run() == first


def test_prospects_skip_the_offseason(client: TestClient, db: Session, league: League,
                                      season: Season):
    _draft_view(client, league)  # generates next year's class
    ages = {p.id: p.age for p in db.scalars(select(Player).where(Player.is_prospect))}
    season.phase = "offseason"
    advance(db, season)
    prospects = db.scalars(select(Player).where(Player.id.in_(ages))).all()
    assert all(p.age == ages[p.id] and p.retired_year is None for p in prospects)


def test_dashboard_during_the_draft(client: TestClient, live: Season):
    alerts = client.get("/api/franchise/dashboard").json()["alerts"]
    assert any("draft is live" in a["message"] for a in alerts)


def test_rookies_join_the_recap(client: TestClient, db: Session, live: Season,
                                franchise: Franchise):
    draft.play(db, live, "end")
    recap = client.get("/api/franchise/dashboard").json()["offseason"]
    picks = [p["draft_pick"] for p in recap["rookies"] if p["draft_pick"]]
    mine = sorted(p.number for p in _picks(db, live) if p.team_id == franchise.team_id)
    kept = {p.id for p in db.scalars(select(Player).where(Player.team_id == franchise.team_id))}
    drafted = [e for e in live.offseason_log["drafted"] if e["team"] == franchise.team_id]
    assert picks == [e["pick"] for e in drafted if e["player"] in kept]
    assert Counter(e["round"] for e in drafted) == Counter(range(1, ROUNDS + 1))
    assert sorted(e["pick"] for e in drafted) == mine
