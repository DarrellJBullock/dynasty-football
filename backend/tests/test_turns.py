"""Leagues with friends, part 2: the season together (docs/design/leagues-with-friends.md §4)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DraftPick, Franchise, Game, League, Season, Team, User
from app.services import accounts, draft, free_agency, jobs, members, turns
from app.services.offseason import advance as run_offseason
from tests.conftest import make_client, sign_in_as


@pytest.fixture
def season(league: League) -> Season:
    return league.seasons[0]


@pytest.fixture
def friend(db: Session, owner: User, league: League,
           franchise: Franchise) -> tuple[User, TestClient, Team]:
    """A second member, running the first team after the owner's, signed in."""
    user = accounts.sign_up(db, "friend@example.test", "friend-password")
    _invite, token = members.create_invite(db, league, owner)
    team = db.scalar(select(Team).where(Team.league_id == league.id,
                                        Team.id != franchise.team_id).order_by(Team.id))
    members.join(db, token, user, team.id)
    db.commit()
    with make_client(db) as client:
        yield user, sign_in_as(client, db, user), team


def _turn(client: TestClient, league: League) -> dict:
    response = client.get(f"/api/leagues/{league.id}/turn")
    assert response.status_code == 200, response.text
    return response.json()


class TestReadyCheckIns:
    def test_managers_say_they_re_ready_and_the_commissioner_sees_it(
            self, client: TestClient, friend, league: League):
        _user, other, team = friend
        turn = _turn(client, league)
        assert turn["step"] == "Week 1" and turn["can_advance"] and not turn["all_ready"]
        assert [(m["team"]["id"], m["ready"]) for m in turn["managers"]][1] == (team.id, False)
        ready = other.put(f"/api/leagues/{league.id}/ready", json={"ready": True}).json()
        assert not ready["can_advance"]
        assert [m["ready"] for m in ready["managers"] if m["is_you"]] == [True]
        client.put(f"/api/leagues/{league.id}/ready", json={"ready": True})
        assert _turn(client, league)["all_ready"]
        other.put(f"/api/leagues/{league.id}/ready", json={"ready": False})
        assert not _turn(client, league)["all_ready"]

    def test_advancing_moves_on_and_everyone_is_unready_again(
            self, db: Session, client: TestClient, friend, league: League, season: Season):
        _user, other, _team = friend
        other.put(f"/api/leagues/{league.id}/ready", json={"ready": True})
        assert other.post(f"/api/leagues/{league.id}/advance").status_code == 403
        turn = client.post(f"/api/leagues/{league.id}/advance").json()
        assert turn["step"] == "Week 2"
        assert not any(m["ready"] for m in turn["managers"])
        week1 = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == 1))
        assert all(g.status == "final" for g in week1)

    def test_a_member_without_a_team_has_nothing_to_be_ready_for(
            self, db: Session, client: TestClient, league: League):
        user = accounts.sign_up(db, "watcher@example.test", "watcher-password")
        members.add(db, league, user, "manager")
        db.commit()
        with make_client(db) as watcher:
            sign_in_as(watcher, db, user)
            response = watcher.put(f"/api/leagues/{league.id}/ready", json={"ready": True})
            assert response.status_code == 403


class TestAdvancing:
    def test_one_step_at_a_time_through_every_phase(self, db: Session, league: League,
                                                    season: Season):
        weeks = turns.season_service.season_weeks(db, season.id)
        labels = [turns.advance(db, league) for _ in range(weeks)]
        assert labels[0] == "Week 1" and labels[-1] == f"Week {weeks}"
        while season.phase != "offseason":
            turns.advance(db, league)
        assert turns.advance(db, league) == "The offseason"
        new = turns.current_season(db, league.id)
        assert new.phase == "free_agency"
        assert turns.step_label(db, new) == "Free agency, day 1"
        assert turns.advance(db, league) == "Free agency, day 1"
        assert new.free_agency_day == 2

    def test_refused_while_a_sim_runs(self, db: Session, league: League):
        jobs.enqueue(db, league, "sim_regular_season")
        with pytest.raises(turns.RosterError, match="simulation is running"):
            turns.advance(db, league)


class TestTheDailyAdvance:
    def test_the_league_advances_itself_once_a_day_at_its_time(self, db: Session,
                                                               client: TestClient,
                                                               league: League):
        nine_pm = 21 * 60
        settings = client.patch(f"/api/leagues/{league.id}/settings",
                                json={"advance_minute_utc": nine_pm}).json()
        assert settings["advance_minute_utc"] == nine_pm and settings["next_advance_at"]
        set_at = league.auto_advanced_at
        today = set_at.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
        before, after = today + timedelta(hours=20), today + timedelta(hours=21, minutes=1)
        if set_at.replace(tzinfo=UTC) >= after:  # (set after today's time: tomorrow's counts)
            before, after = before + timedelta(days=1), after + timedelta(days=1)
        assert turns.tick(db, before) == 0
        assert turns.tick(db, after) == 1
        assert turns.step_label(db, turns.current_season(db, league.id)) == "Week 2"
        assert turns.tick(db, after + timedelta(minutes=5)) == 0  # (once a day)
        assert turns.tick(db, after + timedelta(days=1)) == 1

    def test_turning_it_off_and_bad_settings(self, client: TestClient, league: League):
        url = f"/api/leagues/{league.id}/settings"
        client.patch(url, json={"advance_minute_utc": 60})
        assert client.patch(url, json={"advance_minute_utc": None}).json()[
            "next_advance_at"] is None
        assert client.patch(url, json={"advance_minute_utc": 1440}).status_code == 422
        assert client.patch(url, json={"draft_clock_minutes": 7}).status_code == 422
        assert client.patch(url, json={"draft_clock_minutes": 60}).json()[
            "draft_clock_minutes"] == 60

    def test_only_a_commissioner_changes_the_settings(self, friend, league: League):
        _user, other, _team = friend
        assert other.patch(f"/api/leagues/{league.id}/settings",
                           json={"draft_clock_minutes": 60}).status_code == 403


@pytest.fixture
def drafting(db: Session, season: Season) -> Season:
    """The next season, free agency played, the draft open."""
    season.phase = "offseason"
    new_season = run_offseason(db, season)
    free_agency.play_days(db, new_season, "end")
    db.commit()
    return new_season


class TestTheDraftClock:
    def test_ai_teams_pick_until_a_manager_whose_clock_runs(
            self, db: Session, client: TestClient, friend, league: League, drafting: Season):
        _user, other, team = friend
        humans = members.human_team_ids(db, league.id)
        turns.advance(db, league)  # the draft, up to the first manager on the clock
        pick = draft.on_the_clock(db, drafting)
        assert pick.team_id in humans
        made = db.scalars(select(DraftPick).where(DraftPick.season_id == drafting.id,
                                                  DraftPick.player_id.is_not(None))).all()
        assert all(p.team_id not in humans for p in made)
        ends = draft.clock_ends_at(db, drafting)
        assert ends is not None
        assert abs((ends - datetime.now(UTC)) - timedelta(days=1)) < timedelta(minutes=1)
        view = client.get(f"/api/leagues/{league.id}/draft").json()
        assert view["clock_ends_at"] is not None

    def test_a_manager_s_pick_lets_the_ai_pick_on_to_the_next_manager(
            self, db: Session, client: TestClient, friend, league: League, drafting: Season):
        _user, other, team = friend
        turns.advance(db, league)
        db.commit()
        pick = draft.on_the_clock(db, drafting)
        mine = client if pick.team_id != team.id else other
        board = mine.get(f"/api/leagues/{league.id}/draft").json()
        chosen = board["prospects"][0]["id"]
        assert mine.post(f"/api/leagues/{league.id}/draft/pick",
                         json={"player_id": chosen}).status_code == 200
        db.expire_all()
        up = draft.on_the_clock(db, drafting)
        assert up.number > pick.number and up.team_id in members.human_team_ids(db, league.id)
        between = db.scalars(select(DraftPick).where(
            DraftPick.season_id == drafting.id, DraftPick.number > pick.number,
            DraftPick.number < up.number)).all()
        assert all(p.player_id is not None for p in between)

    def test_when_the_clock_runs_out_the_pick_is_made_for_them(
            self, db: Session, friend, league: League, drafting: Season):
        turns.advance(db, league)
        late = draft.on_the_clock(db, drafting)
        assert draft.run_clock(db, drafting, datetime.now(UTC) + timedelta(hours=23)) == []
        made = draft.run_clock(db, drafting, datetime.now(UTC) + timedelta(days=1, minutes=1))
        assert made[0].id == late.id and late.player_id is not None
        up = draft.on_the_clock(db, drafting)
        assert up is None or up.team_id in members.human_team_ids(db, league.id)

    def test_the_worker_runs_out_clocks(self, db: Session, friend, league: League,
                                        drafting: Season):
        turns.advance(db, league)
        late = draft.on_the_clock(db, drafting)
        db.commit()
        assert turns.tick(db, datetime.now(UTC) + timedelta(days=2)) >= 1
        db.refresh(late)
        assert late.player_id is not None

    def test_a_league_played_alone_has_no_clock(self, db: Session, league: League,
                                                drafting: Season):
        draft.play(db, drafting, "my_pick")
        assert draft.on_the_clock(db, drafting) is not None
        assert draft.clock_ends_at(db, drafting) is None


class TestPlayingTogether:
    def test_a_game_between_two_managers_isn_t_coached(self, db: Session, client: TestClient,
                                                       friend, league: League,
                                                       franchise: Franchise, season: Season):
        _user, _other, team = friend
        game = Game(season_id=season.id, week=1, stage="regular", status="scheduled",
                    home_team_id=franchise.team_id, away_team_id=team.id)
        for existing in db.scalars(select(Game).where(
                Game.season_id == season.id, Game.week == 1,
                (Game.home_team_id.in_([franchise.team_id, team.id]))
                | (Game.away_team_id.in_([franchise.team_id, team.id])))):
            existing.week = 99  # (so this is each team's game this week)
        db.add(game)
        db.commit()
        response = client.post(f"/api/games/{game.id}/coach")
        assert response.status_code == 409
        assert "simulated from both game plans" in response.json()["detail"]

    def test_sim_ahead_is_for_leagues_played_alone(self, client: TestClient, friend,
                                                   league: League):
        response = client.post(f"/api/leagues/{league.id}/jobs",
                               json={"kind": "sim_seasons", "seasons": 2})
        assert response.status_code == 409
        assert "a step at a time" in response.json()["detail"]
