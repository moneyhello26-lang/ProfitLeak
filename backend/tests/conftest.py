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
