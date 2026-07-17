"""
Stage 2: build the two hostelería pipeline outputs from the raw citywide
censo de locales pull (scripts/03_fetch_hosteleria.py):
  A. the ZPAE-relevant competitor point layer, clipped to the four zones.
  B. candidate-address commercial-local context, joined onto Stage 1's
     clipped rt_portalpk_p address points.

Run locally (after scripts/01, 02, and 03 have produced their outputs):
    python scripts/04_reconcile_hosteleria.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from hosteleria import (
    build_competitor_layer,
    join_candidate_context,
    summarize_candidate_context,
)
from zpae_geometry import build_study_area

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
BUFFER_M = 300
JOIN_TOLERANCE_M = 15

raw_gdf = gpd.read_file(RAW_DIR / "hosteleria" / "censo_locales_full.geojson")
records = raw_gdf.drop(columns="geometry").to_dict("records")

# --- A. Competitor layer ---
result = build_competitor_layer(records)
print(f"Competitors: {result.mapped_count} mapped, "
      f"{result.excluded_count} excluded, {result.unmapped_count} unmapped.")

zpae_ambitos = gpd.read_file(RAW_DIR / "zpae" / "zpae_ambitos.geojson")
study_area = build_study_area(zpae_ambitos, buffer_m=BUFFER_M)

competitors_clipped = result.gdf[result.gdf.intersects(study_area)]
print(f"Competitors after clip to study area: "
      f"{len(result.gdf)} -> {len(competitors_clipped)}")
print("Competitors after clip, by decreto_class:")
print(competitors_clipped["decreto_class"].value_counts().to_string())

competitors_out = PROCESSED_DIR / "hosteleria_competitors_zpae_clip.gpkg"
competitors_clipped.to_file(competitors_out, driver="GPKG")
print(f"Saved to {competitors_out}")

# --- B. Candidate address context ---
addresses = gpd.read_file(PROCESSED_DIR / "rt_portalpk_p_zpae_clip.gpkg")
# NOT clipped -- a local just outside the study buffer could still be the
# nearest match to an address right at the buffer edge.
locals_gdf = raw_gdf

joined = join_candidate_context(addresses, locals_gdf, tolerance_m=JOIN_TOLERANCE_M)
match_distances = joined["match_distance_m"].dropna()
print(f"\nMatch distances (m): min={match_distances.min():.1f} "
      f"median={match_distances.median():.1f} "
      f"p95={match_distances.quantile(0.95):.1f} "
      f"max={match_distances.max():.1f}")
unmatched_count = joined["id_local"].isna().sum()
print(f"Addresses with no commercial local within {JOIN_TOLERANCE_M}m: "
      f"{unmatched_count} / {len(addresses)}")

summary = summarize_candidate_context(joined, address_id_col="id_porpk")
summary["current_activity_summary"] = summary["current_activity_summary"].apply(json.dumps)

candidates_out = PROCESSED_DIR / "candidate_addresses_zpae_clip.gpkg"
summary.to_file(candidates_out, driver="GPKG")
print(f"Saved to {candidates_out}")
