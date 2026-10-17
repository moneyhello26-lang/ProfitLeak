"""Run the built app on loopback with persistent SQLite and no external LLM."""

import argparse
import json
import os
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def prepare_environment(database: Path, port: int):
    build = ROOT / "frontend" / "dist"
    if not (build / "index.html").is_file():
        raise SystemExit("Build the frontend first: npm.cmd --prefix frontend run build")
    database = database if database.is_absolute() else ROOT / database
    database = database.resolve()
    if not database.parent.is_dir():
        raise SystemExit("The database directory must exist")
    os.environ.update({
        "DATABASE_URL": "sqlite:///" + database.as_posix(),
        "FRONTEND_DIST": str(build),
        "CORS_ORIGINS": json.dumps([f"http://127.0.0.1:{port}", f"http://localhost:{port}"]),
        "SESSION_COOKIE_SECURE": "false",
        "LLM_ENABLED": "false",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": "",
    })
    return database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--database", type=Path, default=Path("backend/profitleak.db"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError:
            parser.exit(1, f"Port {args.port} is in use. Stop the app or choose another --port.\n")
    database = prepare_environment(args.database, args.port)

    # Configure the process before importing application/database settings.
    import uvicorn
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(ROOT / "backend" / "alembic.ini")), "head")
    print(f"ProfitLeak: http://127.0.0.1:{args.port}", flush=True)
    print(f"SQLite: {database}", flush=True)
    print("Local advisor only. Press Ctrl+C to stop.\n", flush=True)
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
