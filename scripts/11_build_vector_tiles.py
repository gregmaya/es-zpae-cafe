"""
Stage 6: convert Stage 5's candidate viability layer into a PMTiles vector
tileset for the web app, plus a small search index for the address search
bar. See docs/superpowers/specs/2026-07-20-stage6-web-app-design.md.

Requires tippecanoe on PATH (`brew install tippecanoe`).

Run locally:
    python scripts/11_build_vector_tiles.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from web_layer import build_search_index, trim_candidate_properties

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
INPUT_PATH = PROCESSED_DIR / "zpae_viability_map.geojson"

if shutil.which("tippecanoe") is None:
    raise RuntimeError(
        "tippecanoe is not on PATH -- install it first (`brew install "
        "tippecanoe`) before running this script."
    )

if not INPUT_PATH.exists():
    raise RuntimeError(
        f"{INPUT_PATH} not found -- run scripts/09_build_web_layer.py "
        f"first to produce Stage 5's output."
    )

WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

candidates = gpd.read_file(INPUT_PATH)
print(f"Loaded {len(candidates)} candidates.")

search_index = build_search_index(candidates)
search_index_path = WEB_DATA_DIR / "search_index.json"
search_index_path.write_text(json.dumps(search_index))
print(f"Saved {len(search_index)} search index entries to {search_index_path}")

trimmed = json.loads(candidates.to_json())
for feature in trimmed["features"]:
    feature["properties"] = trim_candidate_properties(feature["properties"])

pmtiles_path = WEB_DATA_DIR / "zpae.pmtiles"
result = subprocess.run(
    [
        "tippecanoe",
        "-f",
        "-o", str(pmtiles_path),
        "-l", "candidates",
        "-zg",
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
    ],
    input=json.dumps(trimmed).encode("utf-8"),
    capture_output=True,
)
if result.returncode != 0:
    raise RuntimeError(
        f"tippecanoe failed (exit {result.returncode}):\n"
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )
print(result.stderr.decode("utf-8", errors="replace"))
print(f"Saved vector tileset to {pmtiles_path}")
