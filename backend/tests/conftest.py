"""Test fixtures.

Tests run against SQLite in-memory by default so they need no services. Set
TEST_DATABASE_URL (e.g. postgresql+psycopg://localhost:5432/dynasty_football_test)
to run the same suite against PostgreSQL — `make test` does this.

The sample league is generated once per session; each test runs inside a
transaction that is rolled back, so tests can freely mutate rosters.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app.models import Franchise, League
from app.seed.generator import generate_league

TEST_SEED = 7

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False},
                               poolclass=StaticPool)

        # pysqlite's legacy transaction handling breaks SAVEPOINT rollback; let
        # SQLAlchemy emit BEGIN itself (see SQLAlchemy "Serializable isolation" docs).
        @event.listens_for(engine, "connect")
        def _disable_pysqlite_transactions(dbapi_connection, _record):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine, "begin")
        def _begin(connection):
            connection.exec_driver_sql("BEGIN")
    else:
        engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        generate_league(session, seed=TEST_SEED)
        session.commit()
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint",
                      expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def league(db: Session) -> League:
    return db.query(League).one()


@pytest.fixture
def franchise(db: Session) -> Franchise:
    return db.query(Franchise).one()


def rollover(db: Session, season):
    """Finish `season`'s offseason: roll over, play free agency and the draft to the end
    (the franchise makes no offers and auto-picks), and cut the franchise to 53. Returns
    the new season, in the preseason."""
    from app.models import Franchise as FranchiseModel
    from app.services import draft, free_agency, offseason

    season.phase = "offseason"
    new_season = offseason.advance(db, season)
    free_agency.play_days(db, new_season, "end")
    draft.play(db, new_season, "end")
    franchise = db.scalar(select(FranchiseModel).where(
        FranchiseModel.league_id == new_season.league_id))
    draft.cut_down(db, franchise.team)
    return new_season
