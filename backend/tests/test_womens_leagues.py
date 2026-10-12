import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.domain.positions import Position
from app.models import League, Player, Season
from app.seed import data
from app.seed.generator import BODY, BODY_WOMEN, generate_league
from app.services import draft
from tests.conftest import rollover

# The default league for seed 2026, as generated before women's leagues existed: men's
# leagues must stay byte-identical for a seed (CLAUDE.md, "Generator RNG order").
DEFAULT_LEAGUE_2026 = "5ba09f068dda9eab41bd8c397cb4b6de32d4435cdb62815f20d7a052d07e2cab"


def _fingerprint(players) -> str:
    rows = [(p.first_name, p.last_name, p.position, p.jersey_number, p.age, p.height_in,
             p.weight_lb, p.college, p.overall, p.potential, p.development_trait,
             tuple(sorted(p.ratings.as_dict().items()))) for p in players]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def test_the_default_mens_league_is_unchanged():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        league = generate_league(session, seed=2026)
        session.flush()
        assert league.players == "men"
        players = session.scalars(select(Player).order_by(Player.id)).all()
        assert _fingerprint(players) == DEFAULT_LEAGUE_2026


def _womens_league(client: TestClient) -> dict:
    spec = client.get("/api/leagues/template?conferences=1&divisions=1&teams_per_division=4")
    response = client.post("/api/leagues", json={**spec.json(), "players": "women"})
    assert response.status_code == 201, response.text
    return response.json()


def _looks_like_a_womens_player(player: Player) -> bool:
    low_h, high_h, low_w, high_w = BODY_WOMEN[Position(player.position)]
    return (player.first_name in data.FIRST_NAMES_WOMEN
            and low_h <= player.height_in <= high_h and low_w <= player.weight_lb <= high_w)


def test_a_womens_league_has_womens_names_and_builds(client: TestClient, db: Session):
    franchise = _womens_league(client)
    assert franchise["league"]["players"] == "women"
    players = db.scalars(select(Player).where(Player.league_id == franchise["league"]["id"])).all()
    assert len(players) > 200
    assert all(_looks_like_a_womens_player(p) for p in players)
    # Smaller than the men's game, position by position.
    for position in Position:
        assert BODY_WOMEN[position][1] < BODY[position][1]
        assert BODY_WOMEN[position][3] < BODY[position][3]
    # The roster API carries them like any other.
    roster = client.get(f"/api/teams/{franchise['team']['id']}/roster").json()
    assert {p["first_name"] for p in roster} <= set(data.FIRST_NAMES_WOMEN)


def test_a_womens_league_plays_a_season_and_its_newcomers_are_women(client: TestClient,
                                                                    db: Session):
    franchise = _womens_league(client)
    league = db.get(League, franchise["league"]["id"])
    season = db.get(Season, franchise["season"]["id"])
    played = client.post(f"/api/seasons/{season.id}/simulate",
                         json={"until": "end_of_regular_season"})
    assert played.status_code == 200, played.text
    assert played.json()["games_simulated"] > 0
    assert client.post(f"/api/seasons/{season.id}/simulate",
                       json={"until": "end_of_playoffs"}).status_code == 200

    # The draft class, free agents and offseason refills are women too.
    new_season = rollover(db, season)
    draft.ensure_class(db, league, new_season.year + 1)
    newcomers = db.scalars(select(Player).where(Player.league_id == league.id)).all()
    assert all(_looks_like_a_womens_player(p) for p in newcomers)
    assert any(p.draft_year for p in newcomers)
