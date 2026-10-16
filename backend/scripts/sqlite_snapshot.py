"""Create/restore a consistent SQLite snapshot, always to a NEW file.

Stop the app before restoring. This intentionally never overwrites a live DB.
"""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def snapshot(source: Path, target: Path) -> None:
    source = source.resolve(strict=True)
    target = target.resolve()
    if source == target:
        raise ValueError("Source and destination must differ")
    # Exclusive creation prevents accidentally replacing an existing database.
    with target.open("xb"):
        pass
    try:
        target.chmod(0o600)
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(target)) as copied:
                original.backup(copied)
                if copied.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("SQLite integrity check failed")
                if copied.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("SQLite foreign key check failed")
    except BaseException:
        # Only our newly created, incomplete destination is removed.
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        snapshot(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Snapshot failed: {error}\n")
    print(f"Verified {args.operation}: {args.destination.resolve()}")


if __name__ == "__main__":
    main()
