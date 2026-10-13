"""Export the repeatable 90 day dataset to CSV files."""

import argparse
from pathlib import Path

from app.services.demo import DEMO_VERSION, build_demo_files

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir", type=Path, default=Path("demo_data/taraz_90d"))
options = parser.parse_args()
options.output_dir.mkdir(parents=True, exist_ok=True)
for kind, data in build_demo_files().items():
    path = options.output_dir / f"{DEMO_VERSION}_{kind}.csv"
    path.write_bytes(data)
    print(path)
