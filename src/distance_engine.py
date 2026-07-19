"""
Evaluates a candidate address's classification against its zone's
threshold rule, given precomputed nearest-competitor distances per
classification. See
docs/superpowers/specs/2026-07-19-stage4-distance-engine-design.md.
"""

from dataclasses import dataclass

import geopandas as gpd


@dataclass(frozen=True)
class EvaluationResult:
    strict_pass: bool
    strict_margin_m: float | None
    strict_binding_classification: str | None
    lenient_pass: bool
    lenient_margin_m: float | None
    lenient_binding_classification: str | None
    prohibited_outright: bool
    interpretations_disagree: bool


def evaluate_candidate(
    own_classification: str,
    zone_rules: dict,
    strict_distances: dict,
    lenient_distances: dict,
) -> EvaluationResult:
    """Evaluate one candidate address. own_classification is its own
    street's classification (alta/moderada/baja/sin_superacion).
    zone_rules is a ZpaeZone.rules dict. strict_distances and
    lenient_distances map classification -> nearest competitor distance
    in metres, or are missing/None for a classification with no
    competitor found within the search cutoff (meaning comfortably
    clear, not unknown)."""
    rule = zone_rules.get(own_classification)

    if rule is None:
        # This zone's plan doesn't regulate this classification at all.
        return EvaluationResult(
            strict_pass=True, strict_margin_m=None, strict_binding_classification=None,
            lenient_pass=True, lenient_margin_m=None, lenient_binding_classification=None,
            prohibited_outright=False, interpretations_disagree=False,
        )

    if rule.prohibited_outright:
        return EvaluationResult(
            strict_pass=False, strict_margin_m=None, strict_binding_classification=None,
            lenient_pass=False, lenient_margin_m=None, lenient_binding_classification=None,
            prohibited_outright=True, interpretations_disagree=False,
        )

    def _evaluate_one(distances: dict) -> tuple:
        if not rule.min_distance_m:
            return True, None, None
        margins = {}
        for classification, threshold in rule.min_distance_m.items():
            nearest = distances.get(classification)
            margins[classification] = float("inf") if nearest is None else (nearest - threshold)
        binding_classification = min(margins, key=margins.get)
        binding_margin = margins[binding_classification]
        passed = binding_margin >= 0
        reported_margin = None if binding_margin == float("inf") else binding_margin
        return passed, reported_margin, binding_classification

    strict_pass, strict_margin, strict_binding = _evaluate_one(strict_distances)
    lenient_pass, lenient_margin, lenient_binding = _evaluate_one(lenient_distances)

    return EvaluationResult(
        strict_pass=strict_pass, strict_margin_m=strict_margin,
        strict_binding_classification=strict_binding,
        lenient_pass=lenient_pass, lenient_margin_m=lenient_margin,
        lenient_binding_classification=lenient_binding,
        prohibited_outright=False,
        interpretations_disagree=(strict_pass != lenient_pass),
    )


def build_classification_landuse_gdf(competitors_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filter to competitors with a known classification, ready to feed
    to cityseer's compute_accessibilities as the 'strict' landuse layer
    -- their own real positions, with each competitor's own offset from
    the network folded in automatically by cityseer's internal
    edge-assignment."""
    classified = competitors_gdf[competitors_gdf["classification"].notna()]
    return classified[["classification", "geometry"]].reset_index(drop=True)


def build_lenient_competitor_points(
    competitors_gdf: gpd.GeoDataFrame, nodes_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Build the 'lenient' landuse layer: synthetic points placed exactly
    at each classified competitor's already-snapped network node
    (offset zero by construction), for the network-distance-only
    interpretation. nodes_gdf must have 'node_id' and 'geometry'
    columns (see network.nodes_gdf_from_graph, Stage 3)."""
    classified = competitors_gdf[competitors_gdf["classification"].notna()]
    merged = classified.merge(
        nodes_gdf[["node_id", "geometry"]], left_on="nearest_node_id",
        right_on="node_id", suffixes=("", "_node"),
    )
    return gpd.GeoDataFrame(
        {"classification": merged["classification"].values},
        geometry=merged["geometry_node"].values,
        crs=competitors_gdf.crs,
    )
