"""Milestone 12, part 1: the Hall of Fame and legacy (docs/design/staff-and-legacy.md §4)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import legacy as rules
from app.models import (
    Award,
    Franchise,
    HallOfFameVote,
    League,
    Notification,
    Player,
    PlayerGameStats,
    RetiredNumber,
    Season,
    Team,
    User,
)
from app.schemas import SigningRequest, SimulateRequest
from app.services import legacy, offseason, sharing
from app.services import season as season_service
from app.services.roster import release_player, sign_player

# ---------- the rules ----------

def _career(pid: int, position: str, **stats) -> rules.Career:
    return rules.Career(pid, position, games=100, stats=stats)


def test_production_is_ranked_within_each_position():
    careers = [_career(1, "QB", pass_yds=40_000, pass_td=300), _career(2, "QB", pass_yds=9_000),
               _career(3, "OT", snaps=12_000), _career(4, "OT", snaps=3_000),
               _career(5, "K", fg_made=300, xp_made=400), _career(6, "MLB", tackles=900)]
    ranks = rules.percentiles(careers)
    # The best at each position ranks first, whatever the position's numbers look like.
    assert ranks[1] == ranks[3] == ranks[5] == ranks[6] == 1.0
    assert ranks[2] == ranks[4] == 0.5


def test_the_score_adds_awards_titles_and_seasons():
    career = _career(1, "QB")
    career.awards, career.titles, career.regular_seasons = {"mvp": 2, "opoy": 1}, 2, 15
    expected = 50 * 0.9 + 2 * 12 + 8 + 2 * 4 + 1.5 * rules.SEASONS_COUNTED
    assert rules.score(career, 0.9) == pytest.approx(expected)
    assert rules.case(career).startswith("2× MVP · OPOY · 2 titles · ")
    assert rules.case(career).endswith(" · 15 seasons")


def test_the_ballot_takes_the_best_over_the_bar_a_few_a_year():
    cases = [(_career(pid, "WR"), score) for pid, score in
             [(1, 90), (2, 70), (3, 70), (4, 65), (5, 61), (6, 59), (7, 20)]]
    inducted, misses = rules.ballot(cases)
    assert inducted == [1, 2, 3, 4]  # (CLASS_MAX; a tie goes to the lower id)
    assert misses[:2] == [5, 6] and 7 in misses


def test_a_lineman_s_case_is_his_snaps():
    career = _career(9, "OG", snaps=10_500)
    career.regular_seasons = 11
    assert rules.case(career) == "10,500 snaps · 11 seasons"


# ---------- the vote ----------

@pytest.fixture
def played(db: Session, league: League) -> Season:
    """A week of stats in the sample league."""
    season = league.seasons[0]
    season_service.simulate(db, season, SimulateRequest(until="next_week"))
    db.commit()
    return season


def _top(db: Session, team_id: int | None = None, position: str = "QB") -> Player:
    stmt = (select(Player).join(PlayerGameStats, PlayerGameStats.player_id == Player.id)
            .where(Player.position == position).order_by(PlayerGameStats.pass_yds.desc(),
                                                          Player.id))
    if team_id is not None:
        stmt = stmt.where(PlayerGameStats.team_id == team_id)
    return db.scalars(stmt).first()


def _retire(db: Session, player: Player, year: int, mvps: int = 0, season: Season = None):
    """Retire him in `year`; an MVP makes the case (one week of stats alone won't)."""
    player.retired_year = year
    if mvps:
        db.add(Award(season_id=season.id, award="mvp", player_id=player.id, team_id=None,
                     summary="—"))
    db.flush()


class TestTheVote:
    def test_a_great_career_gets_in_after_the_wait(self, db: Session, league: League,
                                                   played: Season):
        star = _top(db)
        _retire(db, star, played.year - 2, mvps=1, season=played)
        assert legacy.induct(db, league, played.year) == []  # (2 seasons: not yet)
        star.retired_year = played.year - 3
        votes = legacy.induct(db, league, played.year + 1)
        inducted = [v for v in votes if v.inducted]
        assert [v.player_id for v in inducted] == [star.id]
        assert inducted[0].case.startswith("MVP · ")
        assert inducted[0].score >= rules.BAR
        assert legacy.induct(db, league, played.year + 1) == []  # (once a year)
        # Next year, he's already in: not on the ballot again.
        assert star.id not in [v.player_id for v in legacy.induct(db, league, played.year + 2)]

    def test_the_near_misses_are_kept(self, db: Session, league: League, played: Season):
        backups = db.scalars(select(Player).join(PlayerGameStats).where(
            PlayerGameStats.pass_att > 0).order_by(Player.id)).unique().all()[:3]
        for player in backups:
            player.retired_year = played.year - 5
        votes = legacy.induct(db, league, played.year)
        assert votes and not any(v.inducted for v in votes)  # (a week isn't a career)
        view = legacy.hall_of_fame(db, league)
        assert view.ballot_year == played.year and view.members == []
        assert {m.player_id for m in view.near_misses} <= {p.id for p in backups}

    def test_an_ai_team_retires_its_inductee_s_number(self, db: Session, league: League,
                                                      played: Season, franchise: Franchise,
                                                      owner: User, monkeypatch):
        monkeypatch.setattr(rules, "BAR", 0.0)  # (his case is one week long)
        ai_team = db.scalar(select(PlayerGameStats.team_id).where(
            PlayerGameStats.team_id != franchise.team_id, PlayerGameStats.pass_yds > 0))
        star = _top(db, ai_team)
        number = star.jersey_number
        _retire(db, star, played.year - 3, mvps=1, season=played)
        legacy.induct(db, league, played.year)
        assert db.scalar(select(RetiredNumber.number).where(
            RetiredNumber.team_id == ai_team)) == number
        assert db.scalar(select(Notification.title).where(
            Notification.user_id == owner.id, Notification.kind == "legacy")) == (
            f"The {played.year} Hall of Fame class")
        # The number is never issued there again: a new signing wearing it changes.
        team = db.get(Team, ai_team)
        release_player(db, db.scalar(select(Player).where(Player.team_id == ai_team,
                                                          Player.id != star.id)), False)
        signing = db.scalar(select(Player).where(Player.team_id.is_(None),
                                                 Player.retired_year.is_(None),
                                                 Player.is_prospect.is_(False)))
        signing.jersey_number = number
        sign_player(db, team, SigningRequest(player_id=signing.id))
        assert signing.jersey_number != number

    def test_a_member_s_team_is_asked_and_decides(self, db: Session, client: TestClient,
                                                  league: League, played: Season,
                                                  franchise: Franchise, owner: User,
                                                  monkeypatch):
        monkeypatch.setattr(rules, "BAR", 0.0)  # (his case is one week long)
        star = _top(db, franchise.team_id)
        _retire(db, star, played.year - 3, mvps=1, season=played)
        legacy.induct(db, league, played.year)
        db.commit()
        assert db.scalar(select(func.count(RetiredNumber.id))) == 0  # (not automatic)
        asked = db.scalar(select(Notification).where(Notification.user_id == owner.id,
                                                     Notification.title.like("% is in the %")))
        assert asked.link == f"/records?team={franchise.team_id}"
        book = client.get(f"/api/teams/{franchise.team_id}/records").json()
        assert [c["player_id"] for c in book["retire_candidates"]][0] == star.id
        assert book["retire_candidates"][0]["hall_of_fame"]
        retired = client.post(f"/api/teams/{franchise.team_id}/retired-numbers",
                              json={"player_id": star.id})
        assert retired.status_code == 201
        assert retired.json()["retired_numbers"][0]["number"] == star.jersey_number
        again = client.post(f"/api/teams/{franchise.team_id}/retired-numbers",
                            json={"player_id": star.id})
        assert again.status_code == 409
        career = client.get(f"/api/players/{star.id}/career").json()
        assert career["hall_of_fame"] == played.year
        assert career["retired_by"] == [franchise.team.nickname]

    def test_only_retired_players_who_played_there(self, db: Session, client: TestClient,
                                                   played: Season, franchise: Franchise):
        active = _top(db, franchise.team_id)
        url = f"/api/teams/{franchise.team_id}/retired-numbers"
        assert client.post(url, json={"player_id": active.id}).status_code == 409
        elsewhere = db.scalar(select(Player).join(PlayerGameStats).where(
            PlayerGameStats.team_id != franchise.team_id))
        elsewhere.retired_year = played.year - 1
        db.commit()
        refused = client.post(url, json={"player_id": elsewhere.id})
        assert refused.status_code == 409 and "never played for" in refused.json()["detail"]
        # The commissioner can do it for the (AI) team he did play for.
        his = db.scalar(select(PlayerGameStats.team_id).where(
            PlayerGameStats.player_id == elsewhere.id))
        assert client.post(f"/api/teams/{his}/retired-numbers",
                           json={"player_id": elsewhere.id}).status_code == 201

    def test_the_offseason_holds_the_vote(self, db: Session, league: League, monkeypatch):
        held = []
        monkeypatch.setattr(legacy, "induct", lambda db, league, year: held.append(year))
        season = league.seasons[0]
        season.phase = "offseason"
        offseason.advance(db, season)
        assert held == [season.year]


class TestRecordBooks:
    def test_a_team_s_records_are_its_own_games(self, db: Session, client: TestClient,
                                                played: Season, franchise: Franchise):
        book = client.get(f"/api/teams/{franchise.team_id}/records").json()
        passing = next(c for c in book["records"] if c["key"] == "passing_yards")
        mine = set(db.scalars(select(PlayerGameStats.player_id).where(
            PlayerGameStats.team_id == franchise.team_id)))
        assert passing["single_game"] and passing["single_season"] and passing["career"]
        assert {r["player_id"] for r in passing["single_game"]} <= mine
        assert passing["single_game"][0]["value"] == db.scalar(
            select(func.max(PlayerGameStats.pass_yds)).where(
                PlayerGameStats.team_id == franchise.team_id))
        # Someone else's team: the book, but nothing to retire.
        other = db.scalar(select(Team.id).where(Team.id != franchise.team_id))
        assert client.get(f"/api/teams/{other}/records").json()["retire_candidates"] == []


def test_legacy_goes_with_the_league_and_into_the_export(db: Session, league: League,
                                                         played: Season):
    from app.services.leagues import delete_league

    star = _top(db)
    _retire(db, star, played.year - 3, mvps=1, season=played)
    legacy.induct(db, league, played.year)
    data = sharing.export_league(db, league)
    assert data["hall_of_fame"] and data["hall_of_fame"][0]["player_id"] == star.id
    assert "retired_numbers" in data
    delete_league(db, league)
    db.flush()
    assert db.scalar(select(func.count(HallOfFameVote.id))) == 0
    assert db.scalar(select(func.count(RetiredNumber.id))) == 0
