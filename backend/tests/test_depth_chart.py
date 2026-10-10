from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.domain.depth_chart import SLOTS, build_chart, starting_lineup, unit_of
from app.domain.positions import STARTERS, Position
from app.models import Franchise


@dataclass
class FakePlayer:
    id: int
    position: str
    overall: int
    injury_status: str = "healthy"


def ids(players) -> list[int]:
    return [p.id for p in players]


class TestBuildChart:
    def test_uncustomized_slots_are_ordered_by_overall(self):
        players = [FakePlayer(1, "QB", 70), FakePlayer(2, "QB", 85), FakePlayer(3, "QB", 78)]
        assert ids(build_chart(players)[Position.QB]) == [2, 3, 1]

    def test_every_slot_is_present(self):
        assert set(build_chart([])) == set(SLOTS)

    def test_saved_order_wins_and_missing_naturals_are_appended(self):
        players = [FakePlayer(1, "QB", 70), FakePlayer(2, "QB", 85), FakePlayer(3, "QB", 78)]
        chart = build_chart(players, {Position.QB: [1]})
        assert ids(chart[Position.QB]) == [1, 2, 3]

    def test_departed_players_drop_out_of_saved_order(self):
        players = [FakePlayer(1, "QB", 70)]
        assert ids(build_chart(players, {Position.QB: [99, 1]})[Position.QB]) == [1]

    def test_cross_listed_players_appear_in_other_slots(self):
        players = [FakePlayer(1, "CB", 80), FakePlayer(2, "FS", 70)]
        chart = build_chart(players, {Position.FS: [1]})
        assert ids(chart[Position.FS]) == [1, 2]
        assert ids(chart[Position.CB]) == [1]


class TestStartingLineup:
    def test_takes_top_of_chart_up_to_starter_count(self):
        players = [FakePlayer(i, "WR", 60 + i) for i in range(1, 6)]
        lineup = starting_lineup(build_chart(players))
        assert ids(lineup[Position.WR]) == [5, 4, 3]
        assert len(lineup[Position.WR]) == STARTERS[Position.WR]

    def test_skips_injured_players(self):
        players = [FakePlayer(1, "QB", 90, "out"), FakePlayer(2, "QB", 70, "questionable")]
        assert ids(starting_lineup(build_chart(players))[Position.QB]) == [2]

    def test_player_cannot_start_twice(self):
        players = [FakePlayer(1, "OT", 85), FakePlayer(2, "OT", 80), FakePlayer(3, "OT", 75),
                   FakePlayer(4, "OG", 70), FakePlayer(5, "OG", 65)]
        # OT1 also listed first at guard: he starts at OT (earlier slot) only.
        lineup = starting_lineup(build_chart(players, {Position.OG: [1]}))
        assert ids(lineup[Position.OT]) == [1, 2]
        assert ids(lineup[Position.OG]) == [4, 5]

    def test_short_slot_fields_fewer_starters(self):
        lineup = starting_lineup(build_chart([FakePlayer(1, "CB", 80)]))
        assert ids(lineup[Position.CB]) == [1]

    def test_units(self):
        assert unit_of(Position.QB) == "offense"
        assert unit_of(Position.SS) == "defense"
        assert unit_of(Position.P) == "special_teams"


# ---------- API ----------

def _chart(client: TestClient, team_id: int) -> dict:
    response = client.get(f"/api/teams/{team_id}/depth-chart")
    assert response.status_code == 200
    return response.json()


def _slot(chart: dict, slot: str) -> dict:
    return next(s for s in chart["slots"] if s["slot"] == slot)


def _slot_ids(chart: dict, slot: str) -> list[int]:
    return [p["id"] for p in _slot(chart, slot)["players"]]


@pytest.fixture
def team_id(franchise: Franchise) -> int:
    return franchise.team_id


class TestDepthChartApi:
    def test_default_chart(self, client: TestClient, team_id: int):
        chart = _chart(client, team_id)
        assert [s["slot"] for s in chart["slots"]] == [p.value for p in SLOTS]
        qb = _slot(chart, "QB")
        assert qb["customized"] is False
        assert qb["starters"] == 1
        overalls = [p["overall"] for p in qb["players"]]
        assert overalls == sorted(overalls, reverse=True)
        assert qb["starter_ids"] == [qb["players"][0]["id"]]
        # Every rostered player appears at their own position.
        assert sum(len(s["players"]) for s in chart["slots"]) == 53

    def test_reorder_changes_starter_and_team_rating(self, client: TestClient, team_id: int):
        before = _chart(client, team_id)
        order = _slot_ids(before, "QB")[::-1]  # worst QB to the top
        after = client.put(f"/api/teams/{team_id}/depth-chart/QB",
                           json={"player_ids": order}).json()
        assert _slot_ids(after, "QB") == order
        assert _slot(after, "QB")["customized"] is True
        assert _slot(after, "QB")["starter_ids"] == [order[0]]
        assert after["team"]["ratings"]["offense"] < before["team"]["ratings"]["offense"]
        # Persisted
        assert _slot_ids(_chart(client, team_id), "QB") == order

    def test_partial_order_appends_remaining_players(self, client: TestClient, team_id: int):
        qbs = _slot_ids(_chart(client, team_id), "QB")
        chart = client.put(f"/api/teams/{team_id}/depth-chart/QB",
                           json={"player_ids": [qbs[2]]}).json()
        assert _slot_ids(chart, "QB") == [qbs[2], qbs[0], qbs[1]]

    def test_cross_list_player(self, client: TestClient, team_id: int):
        chart = _chart(client, team_id)
        corner = _slot_ids(chart, "CB")[2]
        safeties = _slot_ids(chart, "FS")
        updated = client.put(f"/api/teams/{team_id}/depth-chart/FS",
                             json={"player_ids": [corner, *safeties]}).json()
        assert _slot_ids(updated, "FS") == [corner, *safeties]
        assert _slot(updated, "FS")["starter_ids"] == [corner]

    def test_rejects_duplicates_and_strangers(self, client: TestClient, team_id: int,
                                              league):
        qbs = _slot_ids(_chart(client, team_id), "QB")
        dupes = client.put(f"/api/teams/{team_id}/depth-chart/QB",
                           json={"player_ids": [qbs[0], qbs[0]]})
        assert dupes.status_code == 422
        other = next(t for t in league.teams if t.id != team_id)
        stranger = _slot_ids(_chart(client, other.id), "QB")[0]
        response = client.put(f"/api/teams/{team_id}/depth-chart/QB",
                              json={"player_ids": [stranger]})
        assert response.status_code == 422
        assert "not on this roster" in response.json()["detail"]
        assert client.put(f"/api/teams/{team_id}/depth-chart/XX",
                          json={"player_ids": []}).status_code == 422

    def test_injured_starter_is_skipped(self, client: TestClient, team_id: int):
        starter = _slot(_chart(client, team_id), "QB")["starter_ids"][0]
        client.patch(f"/api/players/{starter}", json={"injury_status": "out"})
        qb = _slot(_chart(client, team_id), "QB")
        assert qb["players"][0]["id"] == starter  # still listed first
        assert qb["starter_ids"] != [starter]

    def test_reset_slot_and_reset_all(self, client: TestClient, team_id: int):
        default = _chart(client, team_id)
        for slot in ("QB", "WR"):
            client.put(f"/api/teams/{team_id}/depth-chart/{slot}",
                       json={"player_ids": _slot_ids(default, slot)[::-1]})
        one = client.delete(f"/api/teams/{team_id}/depth-chart/QB").json()
        assert _slot(one, "QB")["customized"] is False
        assert _slot(one, "WR")["customized"] is True
        assert _slot_ids(one, "QB") == _slot_ids(default, "QB")
        everything = client.delete(f"/api/teams/{team_id}/depth-chart").json()
        assert not any(s["customized"] for s in everything["slots"])
        assert everything["team"]["ratings"] == default["team"]["ratings"]

    def test_released_player_leaves_chart_and_does_not_return(self, client: TestClient,
                                                               team_id: int):
        qbs = _slot_ids(_chart(client, team_id), "QB")
        client.put(f"/api/teams/{team_id}/depth-chart/QB", json={"player_ids": qbs[::-1]})
        released = qbs[-1]  # currently QB1
        client.post(f"/api/players/{released}/release")
        assert released not in _slot_ids(_chart(client, team_id), "QB")
        # Re-signed player goes to the bottom, not back to his old spot.
        client.post(f"/api/teams/{team_id}/signings", json={"player_id": released})
        assert _slot_ids(_chart(client, team_id), "QB")[-1] == released

    def test_position_change_moves_player_between_slots(self, client: TestClient,
                                                        team_id: int):
        chart = _chart(client, team_id)
        te = _slot_ids(chart, "TE")
        client.put(f"/api/teams/{team_id}/depth-chart/TE", json={"player_ids": te[::-1]})
        mover = te[0]
        client.patch(f"/api/players/{mover}", json={"position": "WR"})
        updated = _chart(client, team_id)
        assert mover not in _slot_ids(updated, "TE")
        assert mover in _slot_ids(updated, "WR")

    def test_dashboard_uses_depth_chart(self, client: TestClient, team_id: int):
        before = client.get("/api/franchise/dashboard").json()["team"]["ratings"]
        qbs = _slot_ids(_chart(client, team_id), "QB")
        client.put(f"/api/teams/{team_id}/depth-chart/QB", json={"player_ids": qbs[::-1]})
        after = client.get("/api/franchise/dashboard").json()["team"]["ratings"]
        assert after["offense"] < before["offense"]

    def test_unknown_team(self, client: TestClient):
        assert client.get("/api/teams/999999/depth-chart").status_code == 404
