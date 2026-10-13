import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture(scope="module")
def pg_connection():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    # All DDL and data live in a unique schema in a transaction that is rolled back.
    with engine.connect() as connection:
        transaction = connection.begin()
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
def db(pg_connection):
    test_transaction = pg_connection.begin_nested()
    try:
        with Session(bind=pg_connection, join_transaction_mode="create_savepoint") as session:
            yield session
    finally:
        test_transaction.rollback()
