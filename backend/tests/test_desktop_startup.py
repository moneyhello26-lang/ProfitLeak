import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "start_desktop", Path(__file__).resolve().parents[1] / "scripts" / "start_desktop.py"
)
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


@pytest.fixture
def local_root(monkeypatch, tmp_path):
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<html>local</html>")
    (tmp_path / "backend").mkdir()
    monkeypatch.setattr(desktop, "ROOT", tmp_path)
    for key in (
        "DATABASE_URL", "FRONTEND_DIST", "CORS_ORIGINS", "SESSION_COOKIE_SECURE",
        "LLM_ENABLED", "OPENAI_API_KEY", "GEMINI_API_KEY",
    ):
        monkeypatch.setenv(key, "old-setting")
    return tmp_path


def test_local_start_overrides_cloud_settings_and_uses_persistent_sqlite(local_root):
    database = desktop.prepare_environment(Path("backend/profitleak.db"), 5173)
    assert database == local_root / "backend" / "profitleak.db"
    assert os.environ["DATABASE_URL"] == "sqlite:///" + database.as_posix()
    assert os.environ["LLM_ENABLED"] == "false"
    assert os.environ["OPENAI_API_KEY"] == os.environ["GEMINI_API_KEY"] == ""
    assert os.environ["SESSION_COOKIE_SECURE"] == "false"
    assert os.environ["FRONTEND_DIST"] == str(local_root / "frontend" / "dist")
    assert "http://127.0.0.1:5173" in os.environ["CORS_ORIGINS"]


def test_restore_can_be_opened_at_an_explicit_new_path_and_port(local_root):
    restored = local_root / "restored.db"
    assert desktop.prepare_environment(restored, 8017) == restored
    assert os.environ["DATABASE_URL"] == "sqlite:///" + restored.as_posix()
    assert "http://localhost:8017" in os.environ["CORS_ORIGINS"]


def test_missing_frontend_build_fails_before_starting(local_root):
    (local_root / "frontend" / "dist" / "index.html").unlink()
    with pytest.raises(SystemExit, match="Build the frontend"):
        desktop.prepare_environment(Path("backend/profitleak.db"), 5173)


def test_missing_database_directory_is_not_silently_created(local_root):
    with pytest.raises(SystemExit, match="database directory must exist"):
        desktop.prepare_environment(Path("missing/profitleak.db"), 5173)
