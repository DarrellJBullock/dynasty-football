import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.trades import (
    AI_MARGIN,
    NEED_BONUS,
    TRADE_DEADLINE_WEEK,
    Asset,
    acceptable,
    ai_side,
    pick_value,
    player_value,
)
from app.models import DepthChartEntry, DraftPick, Franchise, League, Player, Season, Trade
from app.services import draft, free_agency
from app.services.offseason import advance

# ---------- pure rules ----------


def test_player_value_curve():
    star = player_value("WR", 90, 27, 90, 20_000_000, 3)
    starter = player_value("WR", 70, 27, 70, 2_000_000, 3)
    assert star > 2 * starter
    assert player_value("WR", 80, 33, 80, 5_000_000, 1) < player_value("WR", 80, 27, 80,
                                                                      5_000_000, 1)
    assert player_value("WR", 70, 22, 88, 1_000_000, 3) > player_value("WR", 70, 27, 70,
                                                                      1_000_000, 3)
    assert player_value("QB", 80, 27, 80, 0, 0) > player_value("K", 80, 27, 80, 0, 0)
    overpaid = player_value("WR", 75, 28, 75, 40_000_000, 3)
    assert overpaid < player_value("WR", 75, 28, 75, 4_000_000, 3)
    assert overpaid >= 0


def test_pick_value_falls_fast():
    assert pick_value(1) == 100
    assert pick_value(1) > pick_value(16) > pick_value(33) > pick_value(100) > 0
    assert pick_value(100) < 10


def test_ai_wants_a_margin_and_pays_for_need():
    gets, wants = ai_side([Asset(100)], [Asset(100)])
    assert wants == pytest.approx(100 * (1 + AI_MARGIN)) and not acceptable(gets, wants)
    gets, wants = ai_side([Asset(100, needed=True)], [Asset(100)])
    assert gets == pytest.approx(100 * (1 + NEED_BONUS)) and acceptable(gets, wants)
    assert acceptable(*ai_side([Asset(5)], []))  # a free player is fine...
    assert not acceptable(*ai_side([], [Asset(5)]))  # ...giving one away isn't


# ---------- the trade center ----------


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


def _center(client: TestClient, league: League, partner_id: int | None = None) -> dict:
    params = {"partner_id": partner_id} if partner_id else {}
    return client.get(f"/api/leagues/{league.id}/trades", params=params).json()


def _evaluate(client: TestClient, league: League, **proposal) -> dict:
    return client.post(f"/api/leagues/{league.id}/trades/evaluate", json=proposal).json()


def _propose(client: TestClient, league: League, **proposal):
    return client.post(f"/api/leagues/{league.id}/trades", json=proposal)


def test_trade_center(client: TestClient, league: League, season: Season, franchise: Franchise):
    center = _center(client, league)
    assert center["closed_reason"] is None and center["deadline_week"] == TRADE_DEADLINE_WEEK
    assert center["draft_year"] == season.year + 1
    assert franchise.team_id not in {t["id"] for t in center["partners"]}
    assert len(center["partners"]) == 31
    for side in ("mine", "theirs"):
        values = [a["value"] for a in center[side]["players"]]
        assert values == sorted(values, reverse=True) and len(values) == 53
        picks = center[side]["picks"]
        assert [p["round"] for p in picks] == list(range(1, 8))
        assert all(p["year"] == season.year + 1 for p in picks)
    partner = center["partners"][5]["id"]
    assert _center(client, league, partner)["partner"]["id"] == partner


def test_lopsided_offers_are_refused(client: TestClient, league: League):
    center = _center(client, league)
    partner = center["partner"]["id"]
    their_best = center["theirs"]["players"][0]["id"]
    my_worst = center["mine"]["players"][-1]["id"]
    verdict = _evaluate(client, league, partner_id=partner, send_players=[my_worst],
                        receive_players=[their_best])
    assert not verdict["acceptable"] and verdict["balance"] < 1
    assert "want more" in verdict["message"]
    response = _propose(client, league, partner_id=partner, send_players=[my_worst],
                        receive_players=[their_best]).json()
    assert response["accepted"] is False and response["trade"] is None


def test_an_accepted_trade_moves_players_and_contracts(
        client: TestClient, db: Session, league: League, franchise: Franchise, season: Season):
    center = _center(client, league)
    partner = center["partner"]["id"]
    mine = center["mine"]["players"][0]  # my most valuable player...
    theirs = center["theirs"]["players"][-1]  # ...for their least
    verdict = _evaluate(client, league, partner_id=partner, send_players=[mine["id"]],
                        receive_players=[theirs["id"]])
    assert verdict["acceptable"] and verdict["balance"] >= 1
    db.add(DepthChartEntry(team_id=franchise.team_id, slot=mine["player"]["position"],
                           depth=1, player_id=mine["id"]))
    db.flush()

    result = _propose(client, league, partner_id=partner, send_players=[mine["id"]],
                      receive_players=[theirs["id"]]).json()
    assert result["accepted"] is True
    sent, received = db.get(Player, mine["id"]), db.get(Player, theirs["id"])
    assert sent.team_id == partner and received.team_id == franchise.team_id
    assert sent.active_contract.team_id == partner
    assert received.active_contract.team_id == franchise.team_id
    assert not db.scalars(select(DepthChartEntry).where(
        DepthChartEntry.player_id == mine["id"])).all()
    roster = db.scalars(select(Player).where(Player.team_id == franchise.team_id)).all()
    assert len({p.jersey_number for p in roster}) == len(roster)

    trade = result["trade"]
    assert trade["partner"]["id"] == partner and trade["season_phase"] == season.phase
    assert [i["id"] for i in trade["sent"]] == [mine["id"]]
    assert [i["id"] for i in trade["received"]] == [theirs["id"]]
    assert _center(client, league)["history"][0]["id"] == trade["id"]


def test_traded_picks_follow_their_original_team(client: TestClient, db: Session,
                                                 league: League, franchise: Franchise,
                                                 season: Season):
    center = _center(client, league)
    partner = center["partner"]["id"]
    my_first = center["mine"]["picks"][0]
    theirs = center["theirs"]["players"][-1]
    my_worst = center["mine"]["players"][-1]  # (so both rosters stay at 53)
    result = _propose(client, league, partner_id=partner, send_picks=[my_first["id"]],
                      send_players=[my_worst["id"]], receive_players=[theirs["id"]]).json()
    assert result["accepted"], result["evaluation"]
    pick = db.get(DraftPick, my_first["id"])
    assert pick.team_id == partner and pick.original_team_id == franchise.team_id
    assert my_first["id"] not in {p["id"] for p in _center(client, league)["mine"]["picks"]}

    # When that draft opens, the pick sits where the franchise finished — owned by the
    # partner, shown as "via".
    season.phase = "offseason"
    next_season = advance(db, season)
    free_agency.play_days(db, next_season, "end")
    assert pick.season_id == next_season.id and pick.number is not None
    view = client.get(f"/api/leagues/{league.id}/draft").json()
    row = next(p for p in view["picks"] if p["number"] == pick.number)
    assert row["team"]["id"] == partner
    assert row["original_team"]["id"] == franchise.team_id
    assert len([p for p in view["picks"] if p["team"]["id"] == franchise.team_id]) == 6


def test_proposals_are_checked(client: TestClient, db: Session, league: League,
                               franchise: Franchise):
    center = _center(client, league)
    partner = center["partner"]["id"]
    their_player = center["theirs"]["players"][0]["id"]
    assert _propose(client, league, partner_id=partner,
                    send_players=[their_player]).status_code == 409  # not mine
    assert _propose(client, league, partner_id=partner).status_code == 409  # empty
    assert _propose(client, league, partner_id=franchise.team_id,
                    send_players=[center["mine"]["players"][0]["id"]]).status_code == 404
    other_year = DraftPick(league_id=league.id, year=2099, round=1,
                           original_team_id=franchise.team_id, team_id=franchise.team_id)
    db.add(other_year)
    db.commit()
    response = _propose(client, league, partner_id=partner, send_picks=[other_year.id])
    assert response.status_code == 409 and "draft can be traded" in response.json()["detail"]


def test_rosters_and_caps_must_work_for_both_sides(client: TestClient, db: Session,
                                                   league: League):
    center = _center(client, league)
    partner = center["partner"]["id"]
    three = [p["id"] for p in center["theirs"]["players"][-3:]]
    verdict = _evaluate(client, league, partner_id=partner,
                        send_players=[center["mine"]["players"][0]["id"]],
                        receive_players=three)
    assert any("roster would have 55" in p for p in verdict["problems"])
    assert not verdict["acceptable"]

    league.salary_cap = 1
    db.commit()
    verdict = _evaluate(client, league, partner_id=partner,
                        send_players=[center["mine"]["players"][-1]["id"]],
                        receive_players=[center["theirs"]["players"][0]["id"]])
    assert any("over the cap" in p for p in verdict["problems"])


def test_giving_a_player_away_is_accepted(client: TestClient, league: League):
    center = _center(client, league)
    result = _propose(client, league, partner_id=center["partner"]["id"],
                      send_players=[center["mine"]["players"][10]["id"]]).json()
    # Their roster is full, so they'd have to be under 53 to take him.
    assert result["accepted"] is False
    assert any("roster would have 54" in p for p in result["evaluation"]["problems"])


@pytest.mark.parametrize("phase, week, closed", [
    ("regular_season", TRADE_DEADLINE_WEEK, False),
    ("regular_season", TRADE_DEADLINE_WEEK + 1, True),
    ("playoffs", 18, True),
    ("offseason", 21, False),
])
def test_trade_window(client: TestClient, db: Session, league: League, season: Season,
                      phase, week, closed):
    season.phase, season.current_week = phase, week
    db.commit()
    center = _center(client, league)
    assert (center["closed_reason"] is not None) == closed
    if closed:
        verdict = _evaluate(client, league, partner_id=center["partner"]["id"],
                            send_players=[center["mine"]["players"][0]["id"]],
                            receive_players=[center["theirs"]["players"][-1]["id"]])
        assert not verdict["acceptable"] and verdict["problems"][0] == center["closed_reason"]


def test_trades_are_closed_during_the_draft(client: TestClient, db: Session, league: League,
                                            season: Season):
    season.phase = "offseason"
    next_season = advance(db, season)
    free_agency.play_days(db, next_season, "end")
    db.commit()
    assert _center(client, league)["closed_reason"] == "Trades are closed during the draft."
    draft.play(db, next_season, "end")
    db.commit()
    center = _center(client, league)
    assert center["closed_reason"] is None and center["draft_year"] == next_season.year + 1


def test_trades_are_deleted_with_their_league(client: TestClient, db: Session, league: League):
    assert db.scalars(select(Trade)).all() == []
