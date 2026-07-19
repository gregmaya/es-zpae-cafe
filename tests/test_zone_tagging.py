import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from zone_tagging import tag_street_classification, tag_zone_membership


def _ambitos_gdf():
    return gpd.GeoDataFrame(
        {"ZPAE": ["ZPAE Centro"]},
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:25830",
    )


def test_tag_zone_membership_inside():
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 50)], crs="EPSG:25830")
    result = tag_zone_membership(points, _ambitos_gdf(), id_col="id")
    assert result.iloc[0]["zpae_zone"] == "ZPAE Centro"


def test_tag_zone_membership_outside():
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(500, 500)], crs="EPSG:25830")
    result = tag_zone_membership(points, _ambitos_gdf(), id_col="id")
    assert pd.isna(result.iloc[0]["zpae_zone"])


def test_tag_street_classification_within_tolerance():
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Alta"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 5)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id")
    assert result.iloc[0]["classification"] == "alta"


def test_tag_street_classification_beyond_max_distance():
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Alta"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 100)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id", max_distance_m=30)
    assert pd.isna(result.iloc[0]["classification"])


def test_tag_street_classification_breaks_ties_by_restrictiveness():
    # two equidistant lines with different classifications -- confirmed
    # this happens in real data (see docs/data_sources.md)
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Baja", "Alta"]},
        geometry=[LineString([(0, 0), (0, 100)]), LineString([(20, 0), (20, 100)])],
        crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(10, 50)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id")
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"  # more restrictive wins the tie


def test_tag_street_classification_dedupes_duplicate_input_rows():
    # mirrors the real Stage 2 data-quality issue: one id, several
    # identical rows (see docs/data_sources.md)
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Moderada"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame(
        {"id": ["dup", "dup", "dup"]},
        geometry=[Point(50, 5), Point(50, 5), Point(50, 5)],
        crs="EPSG:25830",
    )
    result = tag_street_classification(points, clasif, id_col="id")
    assert len(result) == 1
