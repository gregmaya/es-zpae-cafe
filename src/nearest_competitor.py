"""
Looks up the identity (name, activity type, classification, distance,
location) of the nearest classified competitor to a candidate address --
both the one that determines the binding pass/fail margin and the single
closest one overall -- under both the strict and lenient distance
interpretations already computed by src/distance_engine.py. See
docs/superpowers/specs/2026-07-19-nearest-competitor-identity-design.md.
"""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class NearestCompetitor:
    id_local: str
    rotulo: str | None
    desc_epigrafe: str
    classification: str
    distance_m: float
    x: float
    y: float


def _multigraph_edge_weight(u, v, keydict):
    return min(data["geom"].length for data in keydict.values())


def compute_reachable_network_distances(
    graph: nx.Graph, node_id: str, cutoff_m: float,
) -> dict[str, float]:
    """Bounded Dijkstra from node_id over graph, returning
    {reachable_node_id: network_distance} for every node within cutoff_m.
    Shared across multiple find_nearest_competitor-style lookups from the
    same origin, so callers doing several lookups per candidate (e.g.
    strict/lenient x binding/overall) only pay for one search."""
    return nx.single_source_dijkstra_path_length(
        graph, node_id, cutoff=cutoff_m, weight=_multigraph_edge_weight,
    )


def select_nearest_competitor(
    network_distances: dict[str, float],
    competitor_index: dict[str, list[dict]],
    *,
    cutoff_m: float,
    candidate_offset_m: float,
    strict: bool,
    classification_filter: str | None = None,
) -> NearestCompetitor | None:
    """Given precomputed network_distances (from
    compute_reachable_network_distances), find the nearest competitor in
    competitor_index (optionally restricted to classification_filter).
    Distance is pure network distance (lenient) or network distance plus
    both endpoints' door-offsets (strict). Returns None if nothing matches
    within cutoff_m."""
    best: NearestCompetitor | None = None
    for reachable_node, network_distance in network_distances.items():
        for record in competitor_index.get(reachable_node, []):
            if classification_filter is not None and record["classification"] != classification_filter:
                continue
            if strict:
                total_distance = network_distance + candidate_offset_m + record["offset_distance_m"]
            else:
                total_distance = network_distance
            if total_distance > cutoff_m:
                continue
            if best is None or total_distance < best.distance_m or (
                total_distance == best.distance_m and record["id_local"] < best.id_local
            ):
                best = NearestCompetitor(
                    id_local=record["id_local"],
                    rotulo=record["rotulo"],
                    desc_epigrafe=record["desc_epigrafe"],
                    classification=record["classification"],
                    distance_m=total_distance,
                    x=record["x"],
                    y=record["y"],
                )
    return best


def find_nearest_competitor(
    graph: nx.Graph,
    node_id: str,
    competitor_index: dict[str, list[dict]],
    *,
    cutoff_m: float,
    candidate_offset_m: float,
    strict: bool,
    classification_filter: str | None = None,
) -> NearestCompetitor | None:
    """Single-lookup convenience wrapper around
    compute_reachable_network_distances + select_nearest_competitor.
    Callers making several lookups from the same node_id (e.g.
    strict/lenient x binding/overall) should call
    compute_reachable_network_distances once and pass its result to
    select_nearest_competitor directly instead, to avoid redundant
    Dijkstra searches."""
    network_distances = compute_reachable_network_distances(graph, node_id, cutoff_m)
    return select_nearest_competitor(
        network_distances, competitor_index,
        cutoff_m=cutoff_m, candidate_offset_m=candidate_offset_m,
        strict=strict, classification_filter=classification_filter,
    )
