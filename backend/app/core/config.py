from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///" + (ROOT / "backend" / "profitleak.db").as_posix()
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    import_signing_key: SecretStr = SecretStr("profitleak-local-demo-change-before-deployment")
    import_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    @field_validator("database_url")
    @classmethod
    def supported_database(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername not in ("sqlite", "sqlite+pysqlite", "postgresql+psycopg"):
            raise ValueError("Use SQLite or the postgresql+psycopg driver")
        if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
            path = Path(url.database)
            if not path.is_absolute():
                path = ROOT / path
            value = url.set(database=path.as_posix()).render_as_string(hide_password=False)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
