"""
Stage 4: compute network distance from every candidate address to the
nearest relevant competitor (per classification), under both the strict
(door-to-door, offsets included) and lenient (network-distance-only)
interpretations, and evaluate each against its zone's threshold rule.

Run locally (after scripts/07_tag_zones_and_classifications.py has
produced its output):
    python scripts/08_compute_distances.py
"""

import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cityseer.metrics.layers as layers
import cityseer.tools.io as cs_io
import geopandas as gpd
import pandas as pd

from distance_engine import (
    build_classification_landuse_gdf,
    build_lenient_competitor_points,
    evaluate_candidate,
)
from nearest_competitor import (
    build_competitor_node_index,
    compute_reachable_network_distances,
    select_nearest_competitor,
)
from network import nodes_gdf_from_graph
from zones import ZONES

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CRS = "EPSG:25830"
# Safely above the largest real threshold in scope (300m, Centro's
# baja-vs-alta) so "not found within this cutoff" always means "clearly
# passes," never "unknown."
SEARCH_CUTOFF_M = 350
CLASSIFICATION_KEYS = ["alta", "moderada", "baja", "sin_superacion"]

ZONE_BY_NAME = {zone.name: zone for zone in ZONES}

with open(PROCESSED_DIR / "network_graph_zpae.pickle", "rb") as f:
    graph = pickle.load(f)

nodes_gdf, edges_gdf, net_struct = cs_io.network_structure_from_nx(graph)
print(f"Network: {len(nodes_gdf)} nodes.")

candidates = gpd.read_file(PROCESSED_DIR / "candidate_addresses_zpae_tagged.gpkg")
competitors = gpd.read_file(PROCESSED_DIR / "hosteleria_competitors_zpae_tagged.gpkg")

competitor_index = build_competitor_node_index(
    competitors[competitors["classification"].notna()]
)

# --- Strict pass: competitors' real positions (cityseer folds their own
# offset in automatically via edge-assignment) ---
strict_landuse = build_classification_landuse_gdf(competitors)
print(f"Strict landuse layer: {len(strict_landuse)} classified competitors.")
strict_nodes, _ = layers.compute_accessibilities(
    data_gdf=strict_landuse,
    landuse_column_label="classification",
    accessibility_keys=CLASSIFICATION_KEYS,
    nodes_gdf=nodes_gdf,
    network_structure=net_struct,
    distances=[SEARCH_CUTOFF_M],
)

# --- Lenient pass: synthetic competitor points at their own snapped node
# (offset zero by construction) ---
graph_nodes_gdf = nodes_gdf_from_graph(graph, crs=CRS)
lenient_landuse = build_lenient_competitor_points(competitors, graph_nodes_gdf)
print(f"Lenient landuse layer: {len(lenient_landuse)} classified competitors.")
lenient_nodes, _ = layers.compute_accessibilities(
    data_gdf=lenient_landuse,
    landuse_column_label="classification",
    accessibility_keys=CLASSIFICATION_KEYS,
    nodes_gdf=nodes_gdf,
    network_structure=net_struct,
    distances=[SEARCH_CUTOFF_M],
)


def _distances_at_node(nodes_result: gpd.GeoDataFrame, node_id: str) -> dict:
    if node_id not in nodes_result.index:
        return {}
    row = nodes_result.loc[node_id]
    result = {}
    for key in CLASSIFICATION_KEYS:
        col = f"cc_{key}_nearest_max_{SEARCH_CUTOFF_M}"
        value = row[col]
        result[key] = None if pd.isna(value) else float(value)
    return result


evaluable = candidates[candidates["zpae_zone"].notna() & candidates["classification"].notna()]
print(f"Candidates to evaluate: {len(evaluable)} / {len(candidates)} "
      f"(inside a zone AND matched to a classified street).")

results = []
for _, row in evaluable.iterrows():
    zone = ZONE_BY_NAME[row["zpae_zone"]]
    node_id = row["nearest_node_id"]

    strict_distances = _distances_at_node(strict_nodes, node_id)
    strict_distances = {
        k: (v + row["offset_distance_m"] if v is not None else None)
        for k, v in strict_distances.items()
    }
    lenient_distances = _distances_at_node(lenient_nodes, node_id)

    evaluation = evaluate_candidate(
        own_classification=row["classification"],
        zone_rules=zone.rules,
        strict_distances=strict_distances,
        lenient_distances=lenient_distances,
    )

    candidate_offset_m = row["offset_distance_m"]

    # Run the bounded Dijkstra search from this candidate's node exactly
    # once, then scan its result for all four strict/lenient x
    # binding/overall lookups below, instead of re-running the search per
    # lookup.
    network_distances = compute_reachable_network_distances(
        graph, node_id, cutoff_m=SEARCH_CUTOFF_M,
    )

    def _lookup(strict, classification_filter):
        found = select_nearest_competitor(
            network_distances, competitor_index,
            cutoff_m=SEARCH_CUTOFF_M, candidate_offset_m=candidate_offset_m,
            strict=strict, classification_filter=classification_filter,
        )
        if found is None:
            return {"id_local": None, "rotulo": None, "desc_epigrafe": None,
                    "classification": None, "distance_m": None, "x": None, "y": None}
        return {
            "id_local": found.id_local, "rotulo": found.rotulo,
            "desc_epigrafe": found.desc_epigrafe, "classification": found.classification,
            "distance_m": found.distance_m, "x": found.x, "y": found.y,
        }

    # Binding-classification lookups are meaningless when there's no binding
    # classification (rule doesn't apply to this street, or prohibited
    # outright) -- force them null rather than looking up an arbitrary
    # classification, by using the "__none__" sentinel filter directly
    # (avoids running a wasted nearest-of-any-classification search first).
    strict_binding_filter = evaluation.strict_binding_classification
    if strict_binding_filter is None:
        strict_binding_filter = "__none__"
    lenient_binding_filter = evaluation.lenient_binding_classification
    if lenient_binding_filter is None:
        lenient_binding_filter = "__none__"

    nearest_lookups = {
        "strict_nearest_binding": _lookup(True, strict_binding_filter),
        "lenient_nearest_binding": _lookup(False, lenient_binding_filter),
        "strict_nearest_overall": _lookup(True, None),
        "lenient_nearest_overall": _lookup(False, None),
    }

    result_row = {
        "id_porpk": row["id_porpk"],
        "zpae_zone": row["zpae_zone"],
        "classification": row["classification"],
        "strict_pass": evaluation.strict_pass,
        "strict_margin_m": evaluation.strict_margin_m,
        "strict_binding_classification": evaluation.strict_binding_classification,
        "lenient_pass": evaluation.lenient_pass,
        "lenient_margin_m": evaluation.lenient_margin_m,
        "lenient_binding_classification": evaluation.lenient_binding_classification,
        "prohibited_outright": evaluation.prohibited_outright,
        "interpretations_disagree": evaluation.interpretations_disagree,
        "geometry": row["geometry"],
    }
    for prefix, fields in nearest_lookups.items():
        for field_name, value in fields.items():
            result_row[f"{prefix}_{field_name}"] = value
    results.append(result_row)

results_gdf = gpd.GeoDataFrame(results, geometry="geometry", crs=CRS)
print(f"\nResults: {int(results_gdf['strict_pass'].sum())} pass (strict), "
      f"{int((~results_gdf['strict_pass']).sum())} fail (strict).")
print(f"Results: {int(results_gdf['lenient_pass'].sum())} pass (lenient), "
      f"{int((~results_gdf['lenient_pass']).sum())} fail (lenient).")
print(f"Disagreements between interpretations: "
      f"{int(results_gdf['interpretations_disagree'].sum())}")
print(f"Outright-prohibited (Alta zones): "
      f"{int(results_gdf['prohibited_outright'].sum())}")

out_path = PROCESSED_DIR / "distance_evaluation_results.gpkg"
results_gdf.to_file(out_path, driver="GPKG")
print(f"Saved to {out_path}")
