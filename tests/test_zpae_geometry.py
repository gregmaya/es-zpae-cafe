import geopandas as gpd
from shapely.geometry import Polygon

from zpae_geometry import build_study_area


def test_build_study_area_buffers_and_dissolves():
    square1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    square2 = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    gdf = gpd.GeoDataFrame(
        {"ZPAE": ["a", "b"]}, geometry=[square1, square2], crs="EPSG:25830"
    )

    result = build_study_area(gdf, buffer_m=5)

    minx, miny, maxx, maxy = result.bounds
    assert minx == -5
    assert miny == -5
    assert maxx == 35
    assert maxy == 15


def test_build_study_area_reprojects_when_crs_differs():
    # a 1x1 degree box roughly over Madrid in EPSG:4326 -- just needs to
    # not raise and to produce a geometry in metres-scale coordinates
    # after reprojection to EPSG:25830.
    square = Polygon([(-3.71, 40.41), (-3.70, 40.41), (-3.70, 40.42), (-3.71, 40.42)])
    gdf = gpd.GeoDataFrame({"ZPAE": ["a"]}, geometry=[square], crs="EPSG:4326")

    result = build_study_area(gdf, buffer_m=10)

    minx, miny, maxx, maxy = result.bounds
    assert minx > 100000  # EPSG:25830 easting for Madrid is in the ~400000s
    assert maxx < 900000
