from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://profitleak:profitleak_local@127.0.0.1:55432/profitleak"
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    import_signing_key: SecretStr = SecretStr("profitleak-local-demo-change-before-deployment")
    import_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
