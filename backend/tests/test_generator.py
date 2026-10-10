from collections import Counter, defaultdict

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.domain.positions import ROSTER_MAX, ROSTER_TEMPLATE
from app.models import Game, League, Player, Team
from app.seed import data
from app.seed.generator import FREE_AGENT_COUNT, generate_league, round_robin
from app.services.teams import payroll


def _names(seed: int) -> list[str]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        generate_league(session, seed=seed)
        return [p.full_name for p in session.scalars(select(Player).order_by(Player.id))]


def test_generation_is_deterministic():
    assert _names(11) == _names(11)
    assert _names(11) != _names(12)


def test_league_structure(db: Session, league: League):
    assert league.name == data.LEAGUE_NAME
    assert len(league.conferences) == 2
    assert all(len(c.divisions) == 4 for c in league.conferences)
    assert all(len(d.teams) == 4 for c in league.conferences for d in c.divisions)
    assert len(league.teams) == 32
    assert len({t.abbreviation for t in league.teams}) == 32


def test_every_roster_matches_template(db: Session):
    for team in db.scalars(select(Team)):
        counts = Counter(p.position for p in team.players)
        assert len(team.players) == ROSTER_MAX
        assert counts == Counter({pos.value: n for pos, n in ROSTER_TEMPLATE.items()})


def test_jersey_numbers_unique_within_team(db: Session):
    for team in db.scalars(select(Team)):
        numbers = [p.jersey_number for p in team.players]
        assert len(numbers) == len(set(numbers)), team.full_name


def test_every_rostered_player_has_contract_and_ratings(db: Session):
    for player in db.scalars(select(Player).where(Player.team_id.is_not(None))):
        assert player.active_contract is not None
        assert player.ratings is not None
        assert 0 <= player.overall <= 99
        assert player.potential >= player.overall


def test_payrolls_fit_under_cap(db: Session, league: League):
    for team in league.teams:
        assert payroll(team.players) <= league.salary_cap, team.full_name


def test_free_agent_pool(db: Session):
    free_agents = db.scalars(select(Player).where(Player.team_id.is_(None))).all()
    assert len(free_agents) == FREE_AGENT_COUNT
    assert all(p.active_contract is None for p in free_agents)


def test_schedule_is_valid(db: Session, league: League):
    season = league.seasons[0]
    games = db.scalars(select(Game).where(Game.season_id == season.id)).all()
    assert len(games) == 16 * data.REGULAR_SEASON_WEEKS

    weekly: dict[int, list[int]] = defaultdict(list)
    matchups = set()
    home_games: Counter[int] = Counter()
    for game in games:
        weekly[game.week] += [game.home_team_id, game.away_team_id]
        matchups.add(frozenset((game.home_team_id, game.away_team_id)))
        home_games[game.home_team_id] += 1

    for week, teams in weekly.items():
        assert sorted(teams) == sorted(t.id for t in league.teams), f"week {week}"
    assert len(matchups) == len(games), "no team should play the same opponent twice"
    assert all(8 <= home_games[t.id] <= 9 for t in league.teams)


def test_round_robin_rejects_odd_team_count():
    with pytest.raises(ValueError):
        round_robin([1, 2, 3], 2)
