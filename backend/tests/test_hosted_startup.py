import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.types import UTCDateTime

spec = importlib.util.spec_from_file_location(
    "start_hosted", Path(__file__).resolve().parents[1] / "scripts" / "start_hosted.py"
)
hosted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosted)


@pytest.fixture
def environment(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    for key, value in {
        "DATABASE_URL": "postgresql://owner:example@localhost/profitleak?sslmode=require",
        "IMPORT_SIGNING_KEY": "a" * 48,
        "SESSION_COOKIE_SECURE": "true",
        "LLM_ENABLED": "false",
        "FRONTEND_DIST": str(tmp_path),
        "RENDER_EXTERNAL_URL": "https://profitleak-example.onrender.com/",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    return monkeypatch


def test_hosted_environment_uses_secure_shared_origin_and_normalizes_provider_url(environment):
    settings = hosted.prepare_environment()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_url.endswith("?sslmode=require")
    assert settings.cors_origins == ["https://profitleak-example.onrender.com"]
    assert settings.session_cookie_secure is True
    assert settings.llm_enabled is False


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_postgres_url_keeps_encoded_password_and_tls_options(prefix):
    url = prefix + "owner:p%40ss%3Aword@example.test/db?sslmode=require&channel_binding=require"
    normalized = Settings(_env_file=None, database_url=url).database_url
    assert normalized.startswith("postgresql+psycopg://owner:p%40ss%3Aword@")
    assert "sslmode=require" in normalized and "channel_binding=require" in normalized


@pytest.mark.parametrize("key,value,message", [
    ("DATABASE_URL", "", "Set DATABASE_URL"),
    ("DATABASE_URL", "sqlite:///:memory:", "requires PostgreSQL"),
    ("IMPORT_SIGNING_KEY", "short", "IMPORT_SIGNING_KEY"),
    ("IMPORT_SIGNING_KEY", "profitleak-local-demo-change-before-deployment", "IMPORT_SIGNING_KEY"),
    ("SESSION_COOKIE_SECURE", "false", "SESSION_COOKIE_SECURE"),
    ("FRONTEND_DIST", "/definitely-not-a-build", "Build the frontend"),
])
def test_hosted_startup_rejects_unsafe_or_incomplete_configuration(
    environment, key, value, message
):
    environment.setenv(key, value)
    with pytest.raises(SystemExit, match=message):
        hosted.prepare_environment()


def test_invalid_hosted_settings_do_not_print_password(environment):
    environment.setenv("DATABASE_URL", "mysql://owner:private-password@localhost/db")
    with pytest.raises(SystemExit) as error:
        hosted.prepare_environment()
    assert "private-password" not in str(error.value)
    assert "Invalid hosted settings" in str(error.value)


def test_utc_timestamp_is_canonical_after_postgres_read():
    local = datetime(2026, 10, 16, 21, 0, tzinfo=timezone(timedelta(hours=5)))
    result = UTCDateTime().process_result_value(local, None)
    assert result.isoformat() == "2026-10-16T16:00:00+00:00"
    assert UTCDateTime().process_result_value(None, None) is None
