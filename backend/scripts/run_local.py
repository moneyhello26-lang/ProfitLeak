"""Run migrations and both local servers without Docker. Stop with Ctrl+C."""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def free_port(port):
    with socket.socket() as check:
        try:
            check.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Port {port} is already in use. Stop the existing server first.")


def ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Server exited during startup. See its output above.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Startup timed out: {url}")


def main():
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.exists():
        raise SystemExit("Install Node.js and run npm.cmd ci in frontend first. See README.md.")
    free_port(8000)
    free_port(5173)
    # A ready-to-use file database; run configuration still reads other settings from .env.
    environment = os.environ.copy()
    environment["DATABASE_URL"] = "sqlite:///" + (ROOT / "backend/profitleak.db").as_posix()
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    processes = []
    try:
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "backend",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=environment,
        )
        processes.append(backend)
        ready("http://127.0.0.1:8000/api/v1/health", backend)
        frontend = subprocess.Popen(
            [node, str(vite), "--host", "127.0.0.1"],
            cwd=ROOT / "frontend",
            env=environment,
        )
        processes.append(frontend)
        ready("http://127.0.0.1:5173", frontend)
        print("\nProfitLeak is ready: http://127.0.0.1:5173", flush=True)
        print("API: http://127.0.0.1:8000/docs | SQLite: backend/profitleak.db", flush=True)
        print("Press Ctrl+C to stop both servers.\n", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise RuntimeError("A server stopped. See its output above.")
    except KeyboardInterrupt:
        print("\nStopping ProfitLeak...", flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
