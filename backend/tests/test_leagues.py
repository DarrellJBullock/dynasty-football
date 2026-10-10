from collections import Counter, defaultdict

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.positions import ROSTER_MAX
from app.models import Franchise, Game, League, Player, Team
from app.schemas import LeagueCreate
from app.seed.generator import FREE_AGENT_COUNT, league_template, round_robin


def _template(client: TestClient, conferences=1, divisions=2, teams_per_division=3) -> dict:
    response = client.get("/api/leagues/template", params={
        "conferences": conferences, "divisions": divisions,
        "teams_per_division": teams_per_division})
    assert response.status_code == 200, response.text
    return response.json()


def _create(client: TestClient, spec: dict, **overrides):
    return client.post("/api/leagues", json={**spec, "seed": 99, **overrides})


class TestSchedule:
    def test_small_leagues_cycle_to_fill_the_season(self):
        weeks = round_robin(list(range(6)), 17)
        assert len(weeks) == 17
        for pairs in weeks:
            assert sorted(t for pair in pairs for t in pair) == list(range(6))
        home = Counter(home for pairs in weeks for home, _ in pairs)
        assert max(home.values()) - min(home.values()) <= 1
        meetings = Counter(frozenset(pair) for pairs in weeks for pair in pairs)
        assert set(meetings.values()) <= {3, 4}  # 17 weeks over a 5-week rotation


class TestTemplate:
    def test_default_shape_matches_the_shipped_league(self):
        spec = league_template(2, 4, 4)
        teams = spec.teams()
        assert len(teams) == 32
        assert [c.name for c in spec.conferences] == ["Atlantic Conference", "Pacific Conference"]
        assert spec.conferences[0].divisions[0].name == "ATL North"
        assert teams[0].abbreviation == "HFD"

    def test_largest_league_uses_the_extra_pool(self):
        spec = league_template(4, 2, 5)
        assert len({t.abbreviation for t in spec.teams()}) == 40

    def test_api_rejects_impossible_templates(self, client: TestClient):
        assert client.get("/api/leagues/template",
                          params={"conferences": 4, "divisions": 4,
                                  "teams_per_division": 4}).status_code == 422
        assert client.get("/api/leagues/template",
                          params={"conferences": 5}).status_code == 422

    def test_odd_template_is_rejected(self, client: TestClient):
        response = client.get("/api/leagues/template", params={
            "conferences": 1, "divisions": 1, "teams_per_division": 5})
        assert response.status_code == 422
        assert "even number" in response.json()["detail"]


class TestLeagueCreateValidation:
    def _spec(self, **changes) -> dict:
        spec = league_template(1, 2, 3).model_dump()  # 6 teams
        spec.update(changes)
        return spec

    def test_valid_spec(self):
        assert LeagueCreate(**self._spec()).user_team == "HFD"

    @pytest.mark.parametrize("mutate, message", [
        (lambda s: s["conferences"][0]["divisions"][0]["teams"].pop(), "even number"),
        (lambda s: s["conferences"][0]["divisions"][1]["teams"][0].update(abbreviation="hfd"),
         "used twice"),
        (lambda s: s.update(user_team="ZZZ"), "not one of the league's teams"),
        (lambda s: s["conferences"][0]["divisions"][0]["teams"][0].update(
            primary_color="red"), "String should match pattern"),
        (lambda s: s["conferences"][0]["divisions"][0]["teams"][0].update(abbreviation="TOOLONG"),
         "String should match pattern"),
        (lambda s: s.update(salary_cap=1), "greater than or equal"),
    ])
    def test_invalid_specs(self, mutate, message):
        spec = self._spec()
        mutate(spec)
        with pytest.raises(ValidationError, match=message):
            LeagueCreate(**spec)

    def test_too_few_teams(self):
        spec = self._spec()
        for division in spec["conferences"][0]["divisions"]:
            del division["teams"][1:]  # 2 teams left
        with pytest.raises(ValidationError, match="4-40 teams"):
            LeagueCreate(**spec)


class TestCreateLeague:
    def test_creates_generated_league_and_activates_it(self, client: TestClient, db: Session,
                                                      franchise: Franchise):
        spec = _template(client)
        spec["name"] = "Midwest Gridiron Circuit"
        spec["abbreviation"] = "mgc"
        spec["weeks"] = 10
        spec["user_team"] = "bur"
        response = _create(client, spec)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["league"]["abbreviation"] == "MGC"
        assert body["team"]["abbreviation"] == "BUR"
        assert body["name"] == "Lumberjacks Dynasty"

        # The new franchise is now the active one everywhere.
        assert client.get("/api/franchise").json()["id"] == body["id"]
        dashboard = client.get("/api/franchise/dashboard").json()
        assert dashboard["team"]["abbreviation"] == "BUR"
        assert dashboard["team"]["roster_count"] == ROSTER_MAX
        assert len(dashboard["division_standings"]["rows"]) == 3

        league_id = body["league"]["id"]
        teams = db.scalars(select(Team).where(Team.league_id == league_id)).all()
        assert len(teams) == 6
        free_agents = db.scalar(select(func.count(Player.id)).where(
            Player.league_id == league_id, Player.team_id.is_(None)))
        assert free_agents == FREE_AGENT_COUNT

        games = db.scalars(select(Game).join(Game.season).where(
            Game.season.property.mapper.class_.league_id == league_id)).all()
        weekly: dict[int, list[int]] = defaultdict(list)
        for game in games:
            weekly[game.week] += [game.home_team_id, game.away_team_id]
        assert sorted(weekly) == list(range(1, 11))
        assert all(sorted(ids) == sorted(t.id for t in teams) for ids in weekly.values())

    def test_empty_rosters_for_importing(self, client: TestClient):
        spec = _template(client)
        body = _create(client, spec, rosters="empty").json()
        assert client.get(f"/api/teams/{body['team']['id']}/roster").json() == []
        free_agents = client.get(f"/api/leagues/{body['league']['id']}/free-agents").json()
        assert len(free_agents) == FREE_AGENT_COUNT

    def test_custom_identities_and_names(self, client: TestClient):
        spec = _template(client, conferences=2, divisions=1, teams_per_division=2)
        spec["conferences"][0]["name"] = "Mountain Conference"
        spec["conferences"][0]["divisions"][0]["name"] = "Summit Division"
        team = spec["conferences"][0]["divisions"][0]["teams"][0]
        team.update(city="Port Avalon", nickname="Krakens", abbreviation="pav",
                    primary_color="#112233", secondary_color="#AABBCC", stadium="Deepwater Park")
        spec["user_team"] = "PAV"
        body = _create(client, spec).json()
        assert body["team"]["full_name"] == "Port Avalon Krakens"
        assert body["team"]["conference"] == "Mountain Conference"
        assert body["team"]["division"] == "Summit Division"

    def test_same_seed_same_league(self, client: TestClient):
        spec = _template(client)
        a = _create(client, spec).json()
        b = _create(client, spec).json()
        roster_a = client.get(f"/api/teams/{a['team']['id']}/roster").json()
        roster_b = client.get(f"/api/teams/{b['team']['id']}/roster").json()
        assert [p["full_name"] for p in roster_a] == [p["full_name"] for p in roster_b]

    def test_invalid_spec_returns_422(self, client: TestClient):
        spec = _template(client)
        spec["conferences"][0]["divisions"][0]["teams"].pop()
        response = _create(client, spec)
        assert response.status_code == 422
        assert "even number" in response.text


class TestFranchises:
    def test_list_and_switch(self, client: TestClient, franchise: Franchise):
        created = _create(client, _template(client)).json()
        listed = client.get("/api/franchises").json()
        assert [f["id"] for f in listed] == [created["id"], franchise.id]
        assert [f["is_active"] for f in listed] == [True, False]
        assert listed[1]["team_count"] == 32

        response = client.post(f"/api/franchises/{franchise.id}/activate")
        assert response.status_code == 200
        assert client.get("/api/franchise").json()["id"] == franchise.id
        assert client.get("/api/franchises").json()[0]["id"] == franchise.id
        assert client.post("/api/franchises/999999/activate").status_code == 404


class TestTeamUpdate:
    def test_rename_and_recolor(self, client: TestClient, franchise: Franchise):
        response = client.patch(f"/api/teams/{franchise.team_id}", json={
            "city": "New Hartford", "nickname": "Ironsides", "abbreviation": "nhi",
            "primary_color": "#000000", "stadium": "Anvil Field"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["full_name"] == "New Hartford Ironsides"
        assert body["abbreviation"] == "NHI"
        assert body["primary_color"] == "#000000"
        assert body["secondary_color"] == "#C9A227"  # untouched
        assert client.get("/api/franchise").json()["team"]["full_name"] == "New Hartford Ironsides"

    def test_abbreviation_must_be_unique_in_league(self, client: TestClient,
                                                   franchise: Franchise):
        response = client.patch(f"/api/teams/{franchise.team_id}", json={"abbreviation": "PRO"})
        assert response.status_code == 409
        assert "Providence Anchors" in response.json()["detail"]

    def test_same_abbreviation_allowed_in_another_league(self, client: TestClient,
                                                         franchise: Franchise):
        created = _create(client, _template(client)).json()
        response = client.patch(f"/api/teams/{created['team']['id']}", json={"abbreviation": "PRO"})
        assert response.status_code == 409  # PRO is in the template league too
        response = client.patch(f"/api/teams/{created['team']['id']}", json={"abbreviation": "XYZ"})
        assert response.status_code == 200

    @pytest.mark.parametrize("payload", [{"primary_color": "blue"}, {"abbreviation": "A"},
                                         {"city": ""}])
    def test_invalid_updates(self, client: TestClient, franchise: Franchise, payload):
        assert client.patch(f"/api/teams/{franchise.team_id}", json=payload).status_code == 422


class TestDeleteLeague:
    def test_active_league_is_protected(self, client: TestClient, league: League):
        response = client.delete(f"/api/leagues/{league.id}")
        assert response.status_code == 409
        assert "Switch to another franchise" in response.json()["detail"]

    def test_delete_removes_everything(self, client: TestClient, db: Session, league: League,
                                       franchise: Franchise):
        created = _create(client, _template(client)).json()
        new_league_id = created["league"]["id"]
        team_id = created["team"]["id"]
        qbs = [p["id"] for p in client.get(f"/api/teams/{team_id}/roster").json()
               if p["position"] == "QB"]
        client.put(f"/api/teams/{team_id}/depth-chart/QB", json={"player_ids": qbs[::-1]})

        client.post(f"/api/franchises/{franchise.id}/activate")
        assert client.delete(f"/api/leagues/{new_league_id}").status_code == 204

        assert client.get(f"/api/leagues/{new_league_id}").status_code == 404
        assert db.scalar(select(func.count(Player.id)).where(
            Player.league_id == new_league_id)) == 0
        assert [f["id"] for f in client.get("/api/franchises").json()] == [franchise.id]
        # The original league is untouched.
        assert client.get("/api/franchise/dashboard").json()["team"]["roster_count"] == ROSTER_MAX
        assert len(client.get(f"/api/leagues/{league.id}/teams").json()) == 32


def test_empty_roster_league_rates_at_replacement_level(client: TestClient):
    body = _create(client, _template(client), rosters="empty").json()
    ratings = client.get(f"/api/teams/{body['team']['id']}").json()["ratings"]
    assert ratings == {"overall": 40, "offense": 40, "defense": 40, "special_teams": 40}
    alerts = client.get("/api/franchise/dashboard").json()["alerts"]
    assert alerts[0]["level"] == "critical"
    assert alerts[0]["message"].startswith("No available starters — every spot")
