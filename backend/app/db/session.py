from collections.abc import Generator
from functools import lru_cache

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


def make_engine(url: str, **kwargs) -> Engine:
    sqlite = make_url(url).get_backend_name() == "sqlite"
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30}
        if sqlite
        else {"connect_timeout": 3},
        **kwargs,
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, record):
            # Explicit BEGIN makes nested savepoint rollback reliable on Python's sqlite driver.
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

        @event.listens_for(engine, "begin")
        def begin_sqlite(connection):
            connection.exec_driver_sql(
                "BEGIN IMMEDIATE"
                if connection.get_execution_options().get("sqlite_write")
                else "BEGIN"
            )

    return engine


def get_db(request: Request) -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        if get_engine().dialect.name == "sqlite" and request.method == "POST":
            session.connection(execution_options={"sqlite_write": True})
        yield session
