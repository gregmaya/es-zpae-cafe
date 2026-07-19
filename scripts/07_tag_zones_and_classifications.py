"""
Stage 4: tag every candidate address and competitor point with its ZPAE
zone (point-in-polygon) and street classification (nearest classified
street segment, normalized to alta/moderada/baja/sin_superacion).

Run locally (after scripts/01, 02, 05, 06 have produced their outputs):
    python scripts/07_tag_zones_and_classifications.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from zone_tagging import (
    MAX_CLASSIFICATION_DISTANCE_M,
    tag_street_classification,
    tag_zone_membership,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

ambitos = gpd.read_file(RAW_DIR / "zpae" / "zpae_ambitos.geojson")
clasificacion = gpd.read_file(RAW_DIR / "zpae" / "zpae_clasificacion.geojson")

for name, filename, id_col in (
    ("candidates", "candidate_addresses_zpae_snapped.gpkg", "id_porpk"),
    ("competitors", "hosteleria_competitors_zpae_snapped.gpkg", "id_local"),
):
    points = gpd.read_file(PROCESSED_DIR / filename)
    n_input = len(points)
    n_unique_ids = points[id_col].nunique()
    if n_unique_ids != n_input:
        print(f"[!] {name}: {n_input} rows but only {n_unique_ids} unique "
              f"{id_col} values -- {n_input - n_unique_ids} duplicate rows "
              f"in the source data will be collapsed to one during "
              f"tagging (see docs/data_sources.md).")

    tagged = tag_zone_membership(points, ambitos, id_col=id_col)
    tagged = tag_street_classification(tagged, clasificacion, id_col=id_col)

    n_total = len(tagged)
    n_in_zone = tagged["zpae_zone"].notna().sum()
    n_classified = tagged["classification"].notna().sum()
    n_evaluable = (tagged["zpae_zone"].notna() & tagged["classification"].notna()).sum()
    print(f"{name}: {n_total} total, {n_in_zone} inside a ZPAE zone, "
          f"{n_classified} matched to a classified street (within "
          f"{MAX_CLASSIFICATION_DISTANCE_M}m), {n_evaluable} have both "
          f"(fully taggable).")

    out_path = PROCESSED_DIR / filename.replace("_snapped.gpkg", "_tagged.gpkg")
    tagged.to_file(out_path, driver="GPKG")
    print(f"  Saved to {out_path}")
