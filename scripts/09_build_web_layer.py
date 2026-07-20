"""
Stage 5: assemble the single static file the eventual map website loads --
Stage 4's pass/fail + competitor-identity results, joined with a
human-readable address label and today's occupancy context, reprojected
to EPSG:4326. See
docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md.

Run locally (after scripts/08_compute_distances.py has produced its
output -- re-run it first if it predates the nearest-competitor-identity
columns):
    python scripts/09_build_web_layer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from web_layer import join_address_labels, join_occupancy_context, reproject_competitor_locations

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
SOURCE_CRS = "EPSG:25830"
COMPETITOR_LOOKUP_PREFIXES = [
    "strict_nearest_binding", "lenient_nearest_binding",
    "strict_nearest_overall", "lenient_nearest_overall",
]

results = gpd.read_file(PROCESSED_DIR / "distance_evaluation_results.gpkg")
print(f"Loaded {len(results)} evaluated candidates.")

missing_columns = [
    f"{prefix}_id_local" for prefix in COMPETITOR_LOOKUP_PREFIXES
    if f"{prefix}_id_local" not in results.columns
]
if missing_columns:
    raise RuntimeError(
        f"distance_evaluation_results.gpkg is missing competitor-identity "
        f"columns {missing_columns} -- re-run scripts/08_compute_distances.py "
        f"to regenerate it before building the web layer."
    )

portal = gpd.read_file(PROCESSED_DIR / "rt_portalpk_p_zpae_clip.gpkg")
tagged = gpd.read_file(PROCESSED_DIR / "candidate_addresses_zpae_tagged.gpkg")

results = join_address_labels(results, portal)
results = join_occupancy_context(results, tagged)
print(f"After joins: {len(results)} rows, {len(results.columns)} columns.")

for prefix in COMPETITOR_LOOKUP_PREFIXES:
    lons, lats = reproject_competitor_locations(results, f"{prefix}_x", f"{prefix}_y", SOURCE_CRS)
    results[f"{prefix}_lon"] = lons
    results[f"{prefix}_lat"] = lats

results = results.to_crs("EPSG:4326")

out_path = PROCESSED_DIR / "zpae_viability_map.geojson"
results.to_file(out_path, driver="GeoJSON")
print(f"Saved to {out_path}")
