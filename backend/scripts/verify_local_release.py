"""Exercise an unpacked release on isolated SQLite, restart it and restore a backup.

No browser uploads or live provider calls. Existing business data is never opened.
"""

import argparse
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx
from package_local import verify

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(root, database, log):
    port = free_port()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "backend")
    environment["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen([
        sys.executable, str(root / "backend/scripts/start_desktop.py"),
        "--port", str(port), "--database", str(database),
    ], cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10)
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if process.poll() is not None:
            client.close()
            raise RuntimeError("Release server exited; inspect server.log")
        try:
            if client.get("/api/v1/health").status_code == 200:
                return process, client
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    process.terminate()
    process.wait(timeout=10)
    client.close()
    raise RuntimeError("Release server did not start")


def stop(process, client):
    client.close()
    process.terminate()
    process.wait(timeout=10)


def successful(response, status=200):
    if response.status_code != status:
        raise AssertionError(f"Expected HTTP {status}: {response.status_code} {response.text}")
    return response.json()


def login(client, email):
    successful(client.post("/api/v1/auth/login", json={
        "email": email, "password": "Release verification password 2026"}))


def cash_report(client, business):
    return successful(client.get("/api/v1/cash/report", params={
        "business_id": business, "date_from": "2026-10-01", "date_to": "2026-10-31"}))


def tables(database):
    with sqlite3.connect(database) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise AssertionError("Database integrity failure")
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY id').fetchall()
                if name != "alembic_version"
                else connection.execute("SELECT * FROM alembic_version").fetchall()
                for name in names}


def check_archive(archive):
    verify(archive)
    directory = ROOT / ".tmp" / ("final release " + uuid4().hex)
    directory.mkdir(parents=True)
    root = directory / "unpacked project"
    root.mkdir()
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if not (root / name).resolve().is_relative_to(root.resolve()):
                raise ValueError("Unsafe archive path")
        source.extractall(root)
    database = directory / "verification.db"
    email = f"release-{uuid4().hex}@example.test"
    checks = []
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        process, client = start(root, database, log)
        try:
            html = client.get("/cash")
            assert html.status_code == 200 and "text/html" in html.headers["content-type"]
            for asset in re.findall(r'(?:src|href)="(/assets/[^"?]+)', html.text):
                assert client.get(asset).status_code == 200, asset
            assert client.get("/templates/cash_statement.csv").status_code == 200
            assert client.get("/api/v1/missing").status_code == 404
            checks.append("unpacked SPA, direct route, build assets and template")
            successful(client.post("/api/v1/auth/register", json={
                "email": email, "password": "Release verification password 2026",
                "full_name": "Synthetic release check"}), 201)
            business = successful(client.post("/api/v1/businesses", json={
                "name": "Isolated release check", "industry": "retail"}), 201)["id"]
            scope = {"business_id": business}
            account = successful(client.post("/api/v1/cash/accounts", params=scope, json={
                "name": "Test cash", "opening_date": "2026-10-01",
                "opening_balance": "1000.00"}), 201)["id"]
            successful(client.post("/api/v1/cash/entries", params=scope, json={
                "account_id": account, "date": "2026-10-17", "kind": "expense",
                "amount": "10.25", "category": "rent", "reference": "SMOKE-1"}), 201)
            payment = successful(client.post("/api/v1/cash/payments", params=scope, json={
                "account_id": account, "due_date": "2026-10-25", "kind": "expense",
                "amount": "1200.00", "category": "rent", "recurrence": "monthly"}), 201)
            successful(client.post("/api/v1/cash/budgets", params=scope, json={
                "month": "2026-10-01", "category": "rent", "amount": "100.00"}))
            report = cash_report(client, business)
            assert report["closing_balance"] == "989.75"
            assert report["budgets"][0]["remaining"] == "89.75"
            assert report["projection"][-1]["gap_accounts"] == [account]
            checks.append("cash ledger, calendar, account-level gap and budget")
            # Separate session proves the new business remains private.
            with httpx.Client(base_url=str(client.base_url), timeout=10) as outsider:
                successful(outsider.post("/api/v1/auth/register", json={
                    "email": "other-" + email, "password": "Release verification password 2026",
                    "full_name": "Other synthetic account"}), 201)
                assert outsider.get("/api/v1/cash/report", params={**scope,
                    "date_from": "2026-10-01", "date_to": "2026-10-31"}).status_code == 404
            demo = successful(client.post("/api/v1/demo/load"))["business"]["id"]
            successful(client.post("/api/v1/analysis/run", json={"business_id": demo}))
            insights = successful(client.get("/api/v1/insights", params={"business_id": demo}))
            assert insights["total"] == 3
            pdf = client.get("/api/v1/reports/pdf", params={"business_id": demo},
                             headers={"Accept-Language": "kk"})
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            (directory / "demo-kk.pdf").write_bytes(pdf.content)
            checks.append("demo analysis and Kazakh PDF download over HTTP")
        finally:
            stop(process, client)
        process, client = start(root, database, log)
        try:
            login(client, email)
            assert cash_report(client, business) == report
            assert cash_report(client, business)["payments"][0]["id"] == payment["id"]
            checks.append("real server restart preserves account and all cash data")
        finally:
            stop(process, client)
        backup = directory / "backup.db"
        restored = directory / "restored.db"
        for operation, original, destination in (
            ("backup", database, backup), ("restore", backup, restored),
        ):
            subprocess.run([sys.executable, str(root / "backend/scripts/sqlite_snapshot.py"),
                            operation, str(original), str(destination)], check=True, cwd=root)
        assert tables(database) == tables(restored)
        checks.append("backup/restore preserves every row of all 16 tables")
        process, client = start(root, restored, log)
        try:
            login(client, email)
            assert cash_report(client, business) == report
            checks.append("restored database starts and returns matching cash report")
        finally:
            stop(process, client)
    result = {"archive": str(archive.resolve()), "checks": checks,
              "directory": str(directory), "result": "passed"}
    (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    check_archive(parser.parse_args().archive.resolve())
