"""Package source and the built frontend, excluding credentials and local data."""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = (
    "backend", "frontend", "shared", "demo_data", "docs", "deploy", ".github",
    "README.md", "HANDOFF.md", "REQUIREMENTS.md", "DEVELOPMENT_PLAN.md",
    ".env.example", ".gitignore", "start.ps1", "start-local.ps1",
    "docker-compose.yml", "render.yaml", "ProfitLeak_AI_Requirements.docx",
)
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".tmp", ".pytest_cache",
                  ".ruff_cache", "backups", "build"}
EXCLUDED_SUFFIXES = {".db", ".db-wal", ".db-shm", ".db-journal", ".dump", ".pyc",
                     ".pyo", ".tsbuildinfo"}


def package(target: Path):
    build = ROOT / "frontend" / "dist"
    if not (build / "index.html").is_file():
        raise ValueError("Build the frontend before packaging")
    # Git determines source membership, while ignored build assets are included explicitly.
    names = subprocess.check_output([
        "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
        *SOURCE_PATHS,
    ], cwd=ROOT).decode("utf-8").split("\0")
    files = {name: ROOT / name for name in names if name}
    for path in build.rglob("*"):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path
    hashes = {}
    contents = {}
    for name, path in sorted(files.items()):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f"Refusing symlink or external file: {name}")
        if (EXCLUDED_PARTS.intersection(Path(name).parts)
                or path.suffix in EXCLUDED_SUFFIXES
                or path.name.startswith(".env") and path.name != ".env.example"
                or any(part.endswith(".egg-info") for part in Path(name).parts)):
            raise ValueError(f"Unexpected private/generated source file: {name}")
        contents[name] = path.read_bytes()
        hashes[name] = hashlib.sha256(contents[name]).hexdigest()
    manifest = {
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_changes": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT)),
        "created_at": datetime.now(UTC).isoformat(),
        "files": hashes,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
            archive.writestr("LOCAL_RELEASE_MANIFEST.json",
                             json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    verify(target)
    print(f"Archive: {target.resolve()}")
    print(f"Files: {len(hashes)}; bytes: {target.stat().st_size}")
    print(f"SHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}")


def verify(target: Path):
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        manifest = json.loads(archive.read("LOCAL_RELEASE_MANIFEST.json"))
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate ZIP members")
        if set(archive.namelist()) != set(manifest["files"]) | {"LOCAL_RELEASE_MANIFEST.json"}:
            raise ValueError("Manifest membership mismatch")
        for name, expected in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Checksum mismatch: {name}")
        for required in ("start-local.ps1", "frontend/dist/index.html",
                         "backend/migrations/versions/0007_cash_management.py",
                         "frontend/dist/templates/cash_statement.csv"):
            if required not in manifest["files"]:
                raise ValueError(f"Required release file missing: {required}")
        html = archive.read("frontend/dist/index.html").decode("utf-8")
        for asset in re.findall(r'(?:src|href)="(/assets/[^"?]+)', html):
            if "frontend/dist" + asset not in manifest["files"]:
                raise ValueError(f"Frontend asset missing: {asset}")
    print("Verified ZIP integrity and every manifest checksum")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/ProfitLeak_local_2026-10-17-final.zip")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        package(args.output)


if __name__ == "__main__":
    main()
