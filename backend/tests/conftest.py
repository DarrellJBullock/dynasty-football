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

from app.api.access import SESSION_COOKIE
from app.db import Base, get_db
from app.main import create_app
from app.models import Franchise, League, User
from app.seed.generator import generate_league
from app.services.accounts import sign_up, start_session
from app.services.members import give_league

TEST_SEED = 7
OWNER_EMAIL, OWNER_PASSWORD = "owner@example.test", "test-owner-password"

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
        league = generate_league(session, seed=TEST_SEED)
        give_league(session, league, sign_up(session, OWNER_EMAIL, OWNER_PASSWORD))
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


def make_client(db: Session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def sign_in_as(client: TestClient, db: Session, user: User) -> TestClient:
    """Give the client a session for the user (without the slow password check)."""
    client.cookies.set(SESSION_COOKIE, start_session(db, user))
    db.commit()  # (as signing in does: a later rollback mustn't sign the client out)
    return client


@pytest.fixture
def owner(db: Session) -> User:
    """The account that owns the sample league."""
    return db.scalar(select(User).where(User.email == OWNER_EMAIL))


@pytest.fixture
def client(db: Session, owner: User) -> Iterator[TestClient]:
    """An API client signed in as the sample league's owner."""
    with make_client(db) as test_client:
        yield sign_in_as(test_client, db, owner)


@pytest.fixture
def anonymous(db: Session) -> Iterator[TestClient]:
    """An API client that isn't signed in."""
    with make_client(db) as test_client:
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
