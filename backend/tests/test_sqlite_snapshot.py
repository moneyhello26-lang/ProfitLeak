import importlib.util
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "sqlite_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "sqlite_snapshot.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backup_restore_includes_committed_wal_and_survives_independent_changes(tmp_path):
    source = tmp_path / "live.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE totals (amount INTEGER)")
        live.execute("INSERT INTO totals VALUES (224250000)")
        live.commit()
        module.snapshot(source, backup)
        live.execute("DELETE FROM totals")
        live.commit()
        module.snapshot(backup, restored)
    with sqlite3.connect(restored) as copy:
        assert copy.execute("SELECT amount FROM totals").fetchall() == [(224250000,)]
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_never_overwrites_existing_file_or_creates_missing_source(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sample (id INTEGER)")
    target = tmp_path / "existing.db"
    target.write_bytes(b"preserve me")
    with pytest.raises(FileExistsError):
        module.snapshot(source, target)
    assert target.read_bytes() == b"preserve me"
    with pytest.raises(ValueError):
        module.snapshot(source, source)
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        module.snapshot(missing, tmp_path / "new.db")
    assert not missing.exists()


def test_corrupt_source_does_not_leave_successful_looking_backup(tmp_path):
    source = tmp_path / "broken.db"
    source.write_text("not a database", encoding="utf-8")
    target = tmp_path / "backup.db"
    with pytest.raises(sqlite3.DatabaseError):
        module.snapshot(source, target)
    assert not target.exists()
