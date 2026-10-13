"""Run from repository root after installing the backend in the project environment."""

import argparse
import json
from pathlib import Path

from app.main import app

target = Path(__file__).resolve().parents[2] / "shared" / "openapi.json"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--check", action="store_true", help="Fail if the saved contract is stale")
arguments = parser.parse_args()
document = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
if arguments.check:
    if not target.exists() or target.read_text(encoding="utf-8") != document:
        raise SystemExit("API contract is stale; run export_openapi.py without --check")
    print("API contract is up to date")
    raise SystemExit(0)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(document, encoding="utf-8")
print(f"Exported {target}")
