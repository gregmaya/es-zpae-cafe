import geopandas as gpd
from shapely.geometry import LineString

from network import dedupe_by_id_tramo, filter_walkable


def _segments_gdf(rows):
    """rows: list of (id_tramo, situacion, tipovehic, clase) tuples."""
    ids, sits, vehics, clases = zip(*rows)
    return gpd.GeoDataFrame(
        {
            "id_tramo": list(ids),
            "situacion": list(sits),
            "tipovehic": list(vehics),
            "clase": list(clases),
        },
        geometry=[LineString([(0, 0), (10, 0)]) for _ in rows],
        crs="EPSG:25830",
    )


def test_filter_walkable_drops_underground():
    # situacion == 2 is Subterraneo -- real car tunnels, mistagged as
    # pedestrian-accessible in the source data (see Global Constraints).
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 2, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_drops_vehicle_only():
    # tipovehic has a trailing space in the real source data ("001 ", not
    # "001") -- the filter must handle that, not assume it's stripped.
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 1, "001 ", 1002)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_keeps_elevated():
    # situacion == 3 is Elevado -- real pedestrian viaducts, kept.
    gdf = _segments_gdf([("1", 3, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_keeps_surface():
    gdf = _segments_gdf([("1", 1, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_dedupe_by_id_tramo_keeps_first():
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("1", 1, "111 ", 2000)])
    result = dedupe_by_id_tramo(gdf)
    assert len(result) == 1


def test_dedupe_by_id_tramo_keeps_distinct():
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 1, "111 ", 2000)])
    result = dedupe_by_id_tramo(gdf)
    assert len(result) == 2
