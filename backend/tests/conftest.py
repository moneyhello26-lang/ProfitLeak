import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import make_engine


@pytest.fixture(scope="module")
def database_connection(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        path = tmp_path_factory.mktemp("database") / "test.db"
        url = "sqlite:///" + path.as_posix()
    engine = make_engine(url)
    # All DDL and data live in a unique schema in a transaction that is rolled back.
    with engine.connect() as connection:
        transaction = connection.begin()
        if engine.dialect.name == "postgresql":
            schema = "profitleak_test_" + uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "head")
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def db(database_connection):
    test_transaction = database_connection.begin_nested()
    try:
        with Session(bind=database_connection, join_transaction_mode="create_savepoint") as session:
            yield session
    finally:
        test_transaction.rollback()


LEGACY_ACCOUNT_MODULES = {
    "test_advisor_api.py",
    "test_analytics.py",
    "test_database.py",
    "test_demo.py",
    "test_import_api.py",
    "test_insights_api.py",
    "test_planning.py",
    "test_reports_api.py",
}


@pytest.fixture(autouse=True)
def existing_finance_tests_have_an_account(request):
    """Only pre-account financial tests get an explicit dependency override.

    Authentication/authorization tests and any future test module exercise real auth.
    The override grants the test account memberships rather than bypassing access checks.
    """
    if request.path.name not in LEGACY_ACCOUNT_MODULES:
        yield
        return
    from sqlalchemy import exists, select

    from app.api.dependencies import current_user
    from app.main import app
    from app.models import Business, BusinessMembership, User

    session = request.getfixturevalue("db")
    user = User(
        email="finance-fixture@example.test", full_name="Finance fixture", password_hash="test"
    )
    session.add(user)
    session.flush()

    def test_account():
        businesses = session.scalars(
            select(Business.id).where(
                ~exists().where(
                    BusinessMembership.business_id == Business.id,
                    BusinessMembership.user_id == user.id,
                )
            )
        )
        session.add_all(
            BusinessMembership(business_id=id_, user_id=user.id, role="owner") for id_ in businesses
        )
        session.flush()
        return user

    app.dependency_overrides[current_user] = test_account
    try:
        yield
    finally:
        app.dependency_overrides.pop(current_user, None)
