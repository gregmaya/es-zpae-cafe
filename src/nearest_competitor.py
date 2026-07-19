"""
Looks up the identity (name, activity type, classification, distance,
location) of the nearest classified competitor to a candidate address --
both the one that determines the binding pass/fail margin and the single
closest one overall -- under both the strict and lenient distance
interpretations already computed by src/distance_engine.py. See
docs/superpowers/specs/2026-07-19-nearest-competitor-identity-design.md.
"""

import geopandas as gpd
import networkx as nx


def build_competitor_node_index(competitors_gdf: gpd.GeoDataFrame) -> dict[str, list[dict]]:
    """Group competitors by their snapped network node, keeping the
    fields needed for identity lookup and strict/lenient distance math."""
    index: dict[str, list[dict]] = {}
    for _, row in competitors_gdf.iterrows():
        record = {
            "id_local": row["id_local"],
            "rotulo": row["rotulo"],
            "desc_epigrafe": row["desc_epigrafe"],
            "classification": row["classification"],
            "offset_distance_m": row["offset_distance_m"],
            "x": row.geometry.x,
            "y": row.geometry.y,
        }
        index.setdefault(row["nearest_node_id"], []).append(record)
    return index
