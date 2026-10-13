from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


def insert(db, model):
    return sqlite_insert(model) if db.get_bind().dialect.name == "sqlite" else pg_insert(model)
