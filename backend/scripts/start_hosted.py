"""Start the single-process hosted app; migrations run before serving requests."""

import json
import os
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from pydantic import ValidationError

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def prepare_environment() -> Settings:
    # Hosted startup must never fall back to the ephemeral local SQLite file.
    if not os.environ.get("DATABASE_URL", "").strip():
        raise SystemExit("Set DATABASE_URL to your hosted PostgreSQL connection string")
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if external_url and "CORS_ORIGINS" not in os.environ:
        os.environ["CORS_ORIGINS"] = json.dumps([external_url])
    os.environ.setdefault("FRONTEND_DIST", str(ROOT / "frontend" / "dist"))
    os.environ.setdefault("SESSION_COOKIE_SECURE", "true")
    os.environ.setdefault("LLM_ENABLED", "false")
    try:
        settings = Settings()
    except (ValidationError, ValueError):
        # Config validation errors can contain the password-bearing DB URL.
        raise SystemExit("Invalid hosted settings; check server environment variables") from None
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise SystemExit("Hosted startup requires PostgreSQL; SQLite is for local startup")
    key = settings.import_signing_key.get_secret_value()
    if len(key) < 32 or key == "profitleak-local-demo-change-before-deployment":
        raise SystemExit("Set IMPORT_SIGNING_KEY to a random secret of at least 32 characters")
    if not settings.session_cookie_secure:
        raise SystemExit("Hosted startup requires SESSION_COOKIE_SECURE=true and HTTPS")
    if not settings.frontend_dist or not (settings.frontend_dist / "index.html").is_file():
        raise SystemExit("Build the frontend before starting the hosted app")
    return settings


def main():
    prepare_environment()
    command.upgrade(Config(str(ROOT / "backend" / "alembic.ini")), "head")
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
        workers=1, proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
