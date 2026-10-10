from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.positions import ROSTER_MAX
from app.domain.ratings import ATTRIBUTES
from app.models import Franchise, League, Player


def _roster(client: TestClient, team_id: int) -> list[dict]:
    response = client.get(f"/api/teams/{team_id}/roster")
    assert response.status_code == 200
    return response.json()


def _free_agent(db: Session) -> Player:
    return db.scalars(select(Player).where(Player.team_id.is_(None)).order_by(Player.id)).first()


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


class TestFranchise:
    def test_franchise(self, client: TestClient, franchise: Franchise):
        body = client.get("/api/franchise").json()
        assert body["name"] == franchise.name
        assert body["team"]["abbreviation"] == "HFD"
        assert body["season"]["phase"] == "preseason"

    def test_dashboard(self, client: TestClient, franchise: Franchise):
        body = client.get("/api/franchise/dashboard").json()
        team = body["team"]
        assert team["id"] == franchise.team_id
        assert team["roster_count"] == ROSTER_MAX
        assert team["payroll"] + team["cap_space"] == body["franchise"]["league"]["salary_cap"]
        assert 40 <= team["ratings"]["overall"] <= 99
        assert body["record"] == {"wins": 0, "losses": 0, "ties": 0}
        assert len(body["division_standings"]["rows"]) == 4
        assert len(body["upcoming_games"]) == 5
        assert all(franchise.team_id in (g["home"]["id"], g["away"]["id"])
                   for g in body["upcoming_games"])
        overalls = [p["overall"] for p in body["top_players"]]
        assert overalls == sorted(overalls, reverse=True)
        assert {g["group"] for g in body["position_groups"]} == {
            "QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "ST"}


class TestLeague:
    def test_list_and_read(self, client: TestClient, league: League):
        assert [lg["id"] for lg in client.get("/api/leagues").json()] == [league.id]
        assert client.get(f"/api/leagues/{league.id}").json()["abbreviation"] == "DFL"
        assert client.get("/api/leagues/999999").status_code == 404

    def test_teams(self, client: TestClient, league: League):
        teams = client.get(f"/api/leagues/{league.id}/teams").json()
        assert len(teams) == 32
        assert all(t["cap_space"] >= 0 for t in teams)

    def test_standings(self, client: TestClient, league: League):
        divisions = client.get(f"/api/leagues/{league.id}/standings").json()
        assert len(divisions) == 8
        assert sum(len(d["rows"]) for d in divisions) == 32

    def test_free_agents_filter(self, client: TestClient, league: League):
        all_fas = client.get(f"/api/leagues/{league.id}/free-agents").json()
        qbs = client.get(f"/api/leagues/{league.id}/free-agents?position=QB").json()
        assert all(p["team_id"] is None for p in all_fas)
        assert all(p["position"] == "QB" for p in qbs)
        assert len(qbs) < len(all_fas)


class TestRoster:
    def test_roster_sorted_by_overall(self, client: TestClient, franchise: Franchise):
        roster = _roster(client, franchise.team_id)
        assert len(roster) == ROSTER_MAX
        assert [p["overall"] for p in roster] == sorted((p["overall"] for p in roster),
                                                        reverse=True)
        assert all(p["contract"] is not None for p in roster)

    def test_player_detail_includes_all_ratings(self, client: TestClient,
                                                franchise: Franchise):
        player_id = _roster(client, franchise.team_id)[0]["id"]
        body = client.get(f"/api/players/{player_id}").json()
        assert set(body["ratings"]) == set(ATTRIBUTES)
        assert client.get("/api/players/999999").status_code == 404

    def test_update_ratings_recomputes_overall(self, client: TestClient, franchise: Franchise):
        qb = next(p for p in _roster(client, franchise.team_id) if p["position"] == "QB")
        maxed = {"throw_power": 99, "throw_accuracy": 99, "awareness": 99,
                 "speed": 99, "agility": 99}
        body = client.patch(f"/api/players/{qb['id']}", json={"ratings": maxed}).json()
        assert body["overall"] == 99
        assert body["potential"] == 99
        assert body["ratings"]["throw_power"] == 99

    def test_update_bio_fields(self, client: TestClient, franchise: Franchise):
        player = _roster(client, franchise.team_id)[-1]
        response = client.patch(f"/api/players/{player['id']}",
                                json={"first_name": "Rookie", "injury_status": "questionable"})
        assert response.status_code == 200
        assert response.json()["full_name"] == f"Rookie {player['last_name']}"
        assert response.json()["injury_status"] == "questionable"

    def test_every_injury_status_can_be_saved(self, client: TestClient, franchise: Franchise):
        # Regression: injured_reserve (15 chars) overflowed a 12-char column on PostgreSQL.
        player_id = _roster(client, franchise.team_id)[0]["id"]
        for status in ("questionable", "out", "injured_reserve", "healthy"):
            response = client.patch(f"/api/players/{player_id}", json={"injury_status": status})
            assert response.status_code == 200, status
            assert response.json()["injury_status"] == status

    def test_position_change_recomputes_overall(self, client: TestClient,
                                                franchise: Franchise):
        kicker = next(p for p in _roster(client, franchise.team_id) if p["position"] == "K")
        body = client.patch(f"/api/players/{kicker['id']}", json={"position": "MLB"}).json()
        assert body["position"] == "MLB"
        assert body["overall"] < kicker["overall"]

    def test_jersey_conflict_rejected(self, client: TestClient, franchise: Franchise):
        a, b = _roster(client, franchise.team_id)[:2]
        response = client.patch(f"/api/players/{a['id']}",
                                json={"jersey_number": b["jersey_number"]})
        assert response.status_code == 409
        assert "already worn" in response.json()["detail"]

    def test_invalid_ratings_rejected(self, client: TestClient, franchise: Franchise):
        player_id = _roster(client, franchise.team_id)[0]["id"]
        too_high = client.patch(f"/api/players/{player_id}", json={"ratings": {"speed": 120}})
        unknown = client.patch(f"/api/players/{player_id}", json={"ratings": {"mojo": 50}})
        assert too_high.status_code == 422
        assert unknown.status_code == 422

    def test_release_then_resign(self, client: TestClient, franchise: Franchise):
        player = _roster(client, franchise.team_id)[-1]
        released = client.post(f"/api/players/{player['id']}/release").json()
        assert released["team_id"] is None
        assert released["contract"] is None
        assert len(_roster(client, franchise.team_id)) == ROSTER_MAX - 1
        assert client.post(f"/api/players/{player['id']}/release").status_code == 409

        signed = client.post(f"/api/teams/{franchise.team_id}/signings",
                             json={"player_id": player["id"], "years": 2})
        assert signed.status_code == 200
        assert signed.json()["contract"]["years"] == 2
        assert len(_roster(client, franchise.team_id)) == ROSTER_MAX

    def test_signing_blocked_when_roster_full(self, client: TestClient, db: Session,
                                              franchise: Franchise):
        response = client.post(f"/api/teams/{franchise.team_id}/signings",
                               json={"player_id": _free_agent(db).id})
        assert response.status_code == 409
        assert "roster is full" in response.json()["detail"]

    def test_signing_blocked_over_cap(self, client: TestClient, db: Session,
                                      franchise: Franchise):
        cut = _roster(client, franchise.team_id)[-1]
        client.post(f"/api/players/{cut['id']}/release")
        response = client.post(f"/api/teams/{franchise.team_id}/signings",
                               json={"player_id": _free_agent(db).id, "salary": 400_000_000})
        assert response.status_code == 409
        assert "salary cap" in response.json()["detail"]

    def test_cannot_sign_rostered_player(self, client: TestClient, franchise: Franchise,
                                         league: League):
        other = next(t for t in league.teams if t.id != franchise.team_id)
        target = _roster(client, other.id)[0]
        cut = _roster(client, franchise.team_id)[-1]
        client.post(f"/api/players/{cut['id']}/release")
        response = client.post(f"/api/teams/{franchise.team_id}/signings",
                               json={"player_id": target["id"]})
        assert response.status_code == 409

    def test_signing_reassigns_conflicting_jersey(self, client: TestClient, db: Session,
                                                  franchise: Franchise):
        roster = _roster(client, franchise.team_id)
        cut = roster[-1]
        client.post(f"/api/players/{cut['id']}/release")
        free_agent = _free_agent(db)
        free_agent.jersey_number = roster[0]["jersey_number"]
        db.flush()
        body = client.post(f"/api/teams/{franchise.team_id}/signings",
                           json={"player_id": free_agent.id}).json()
        numbers = [p["jersey_number"] for p in _roster(client, franchise.team_id)]
        assert body["jersey_number"] != roster[0]["jersey_number"]
        assert len(numbers) == len(set(numbers))

    def test_create_player(self, client: TestClient, franchise: Franchise):
        cut = _roster(client, franchise.team_id)[-1]
        client.post(f"/api/players/{cut['id']}/release")
        payload = {"first_name": "Custom", "last_name": "Prospect", "position": "WR",
                   "jersey_number": cut["jersey_number"],
                   "ratings": {"speed": 95, "catching": 90, "route_running": 88}}
        response = client.post(f"/api/teams/{franchise.team_id}/players", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["ratings"]["speed"] == 95
        assert body["ratings"]["stamina"] == 50  # unspecified attributes default to 50
        assert body["contract"]["salary"] > 0

    def test_create_player_validation(self, client: TestClient, franchise: Franchise):
        bad = {"first_name": "", "last_name": "X", "position": "QB", "jersey_number": 120}
        assert client.post(f"/api/teams/{franchise.team_id}/players",
                           json=bad).status_code == 422
        bad_position = {"first_name": "A", "last_name": "B", "position": "LS",
                        "jersey_number": 48}
        assert client.post(f"/api/teams/{franchise.team_id}/players",
                           json=bad_position).status_code == 422

    def test_create_player_blocked_when_roster_full(self, client: TestClient,
                                                    franchise: Franchise):
        payload = {"first_name": "Extra", "last_name": "Body", "position": "QB",
                   "jersey_number": 0}
        response = client.post(f"/api/teams/{franchise.team_id}/players", json=payload)
        assert response.status_code == 409
