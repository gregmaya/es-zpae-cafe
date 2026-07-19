import geopandas as gpd
import networkx as nx
from shapely.geometry import Point, LineString

from nearest_competitor import build_competitor_node_index, find_nearest_competitor


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


def _line_graph():
    g = nx.MultiGraph()
    coords = {"n0": (0, 0), "n1": (10, 0), "n2": (20, 0), "n3": (30, 0)}
    for node_id, (x, y) in coords.items():
        g.add_node(node_id, x=x, y=y)
    for u, v in [("n0", "n1"), ("n1", "n2"), ("n2", "n3")]:
        (x1, y1), (x2, y2) = coords[u], coords[v]
        g.add_edge(u, v, geom=LineString([(x1, y1), (x2, y2)]))
    return g


def test_find_nearest_competitor_lenient_picks_closest_by_network_distance():
    graph = _line_graph()
    index = {
        "n2": [{
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "moderada", "offset_distance_m": 5.0, "x": 20.0, "y": 0.0,
        }],
        "n3": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 30.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
    )
    # n2 is 20m away (network), n3 is 30m away -- n2's competitor wins
    # despite its larger offset_distance_m, because lenient ignores offsets.
    assert result.id_local == "1"
    assert result.distance_m == 20.0


def test_find_nearest_competitor_respects_cutoff():
    graph = _line_graph()
    index = {
        "n3": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 30.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=25, candidate_offset_m=0.0, strict=False,
    )
    # n3 is 30m away, beyond the 25m cutoff -- nothing found.
    assert result is None


def test_find_nearest_competitor_classification_filter_excludes_non_matching():
    graph = _line_graph()
    index = {
        "n1": [{
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "alta", "offset_distance_m": 0.0, "x": 10.0, "y": 0.0,
        }],
        "n2": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
        classification_filter="moderada",
    )
    # Closer competitor (n1, alta) is filtered out; moderada one at n2 wins.
    assert result.id_local == "2"
    assert result.distance_m == 20.0


def test_find_nearest_competitor_tie_break_lowest_id_local():
    graph = _line_graph()
    index = {
        "n2": [
            {
                "id_local": "9", "rotulo": "Bar Nueve", "desc_epigrafe": "CAFETERIA",
                "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
            },
            {
                "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
                "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
            },
        ],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
    )
    assert result.id_local == "2"
