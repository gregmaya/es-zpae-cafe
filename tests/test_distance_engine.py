from distance_engine import evaluate_candidate
from zones import ClassificationRule


def test_evaluate_candidate_prohibited_outright():
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("alta", zone_rules, strict_distances={}, lenient_distances={})
    assert result.prohibited_outright is True
    assert result.strict_pass is False
    assert result.lenient_pass is False


def test_evaluate_candidate_classification_not_in_rules_is_unregulated():
    # e.g. sin_superacion in most zones -- not mentioned in the rules
    # dict at all, meaning no ZPAE distance rule applies to it
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("sin_superacion", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.lenient_pass is True
    assert result.prohibited_outright is False


def test_evaluate_candidate_passes_when_all_competitors_far():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 90, "baja": 60},
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    # margins: alta 150-100=50, moderada 90-75=15, baja 60-50=10 -> baja binds
    assert result.strict_pass is True
    assert result.strict_margin_m == 10
    assert result.strict_binding_classification == "baja"


def test_evaluate_candidate_fails_when_a_competitor_too_close():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 60, "baja": 60},  # moderada margin = -15
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    assert result.strict_pass is False
    assert result.strict_margin_m == -15
    assert result.strict_binding_classification == "moderada"
    assert result.lenient_pass is True
    assert result.interpretations_disagree is True


def test_evaluate_candidate_no_competitor_found_within_search_range():
    zone_rules = {
        "baja": ClassificationRule(min_distance_m={"alta": 150, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate("baja", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.strict_margin_m is None
    assert result.lenient_pass is True


import geopandas as gpd
from shapely.geometry import Point

from distance_engine import build_classification_landuse_gdf, build_lenient_competitor_points


def test_build_classification_landuse_gdf_drops_unclassified():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta", None]},
        geometry=[Point(0, 0), Point(10, 10)],
        crs="EPSG:25830",
    )
    result = build_classification_landuse_gdf(competitors)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"


def test_build_lenient_competitor_points_uses_node_coordinates():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta"], "nearest_node_id": ["n1"]},
        geometry=[Point(5, 5)],  # real position, offset from the node
        crs="EPSG:25830",
    )
    nodes_gdf = gpd.GeoDataFrame(
        {"node_id": ["n1"]}, geometry=[Point(0, 0)], crs="EPSG:25830",
    )
    result = build_lenient_competitor_points(competitors, nodes_gdf)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"
    assert result.iloc[0].geometry.x == 0.0
    assert result.iloc[0].geometry.y == 0.0


def test_build_lenient_competitor_points_drops_unclassified():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta", None], "nearest_node_id": ["n1", "n2"]},
        geometry=[Point(5, 5), Point(50, 50)],
        crs="EPSG:25830",
    )
    nodes_gdf = gpd.GeoDataFrame(
        {"node_id": ["n1", "n2"]}, geometry=[Point(0, 0), Point(40, 40)], crs="EPSG:25830",
    )
    result = build_lenient_competitor_points(competitors, nodes_gdf)
    assert len(result) == 1
