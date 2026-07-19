import geopandas as gpd
from shapely.geometry import Point

from nearest_competitor import build_competitor_node_index


def _competitors_gdf(rows):
    """rows: list of (id_local, rotulo, desc_epigrafe, classification,
    nearest_node_id, offset_distance_m, x, y) tuples."""
    records = [
        {
            "id_local": r[0], "rotulo": r[1], "desc_epigrafe": r[2],
            "classification": r[3], "nearest_node_id": r[4],
            "offset_distance_m": r[5],
        }
        for r in rows
    ]
    geometry = [Point(r[6], r[7]) for r in rows]
    return gpd.GeoDataFrame(records, geometry=geometry, crs="EPSG:25830")


def test_build_competitor_node_index_groups_by_node():
    gdf = _competitors_gdf([
        ("1", "Bar Uno", "BAR SIN COCINA", "moderada", "nodeA", 2.5, 100.0, 200.0),
        ("2", "Bar Dos", "BAR CON COCINA", "alta", "nodeA", 1.0, 101.0, 201.0),
        ("3", "Bar Tres", "CAFETERIA", "baja", "nodeB", 0.5, 300.0, 400.0),
    ])
    index = build_competitor_node_index(gdf)
    assert set(index.keys()) == {"nodeA", "nodeB"}
    assert len(index["nodeA"]) == 2
    assert len(index["nodeB"]) == 1
    record = index["nodeB"][0]
    assert record["id_local"] == "3"
    assert record["rotulo"] == "Bar Tres"
    assert record["desc_epigrafe"] == "CAFETERIA"
    assert record["classification"] == "baja"
    assert record["offset_distance_m"] == 0.5
    assert record["x"] == 300.0
    assert record["y"] == 400.0
