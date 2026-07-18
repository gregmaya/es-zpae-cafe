"""
Builds Stage 3's Cityseer-compatible walkable network graph from the
clipped IGR-RT street segments, and snaps Stage 2's point layers onto it.
See docs/superpowers/specs/2026-07-18-stage3-network-graph-design.md.
"""

import geopandas as gpd
from shapely.geometry import Point


def filter_walkable(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop segments that aren't real pedestrian routes: underground
    tunnels (situacion == 2 -- confirmed via manual inspection to be real
    Madrid car tunnels such as Princesa, Bailen, San Vicente, and the
    A-5/A-6/M-30 ring, even though most are mistagged as
    pedestrian-accessible), vehicle-only segments, and motorway-class
    segments. Elevated segments (situacion == 3, e.g. real pedestrian
    viaducts) and surface segments (situacion == 1) are kept."""
    walkable = gdf["situacion"] != 2
    walkable &= gdf["tipovehic"].str.strip() != "001"
    walkable &= gdf["clase"] != 1002
    return gdf[walkable]


def dedupe_by_id_tramo(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """rt_tramo_vial joins segments to street names, so a segment shared
    by two named streets appears as two identical-geometry rows under the
    same id_tramo. Keep one row per physical segment, or the graph would
    double-count these edges."""
    return gdf.drop_duplicates(subset="id_tramo", keep="first")


def nodes_gdf_from_graph(graph, crs: str) -> gpd.GeoDataFrame:
    """Extract a graph's nodes as a point GeoDataFrame, keyed by the
    networkx node id (a string like 'x123.4-y456.7' for cityseer-built
    graphs)."""
    records = [
        {"node_id": node_id, "geometry": Point(data["x"], data["y"])}
        for node_id, data in graph.nodes(data=True)
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def snap_points_to_nearest_node(
    points_gdf: gpd.GeoDataFrame, nodes_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Snap every point to its nearest graph node. Returns points_gdf with
    two new columns: nearest_node_id, offset_distance_m -- Stage 4 adds
    this offset back into the final network-distance calculation rather
    than dropping that precision."""
    joined = gpd.sjoin_nearest(
        points_gdf, nodes_gdf[["node_id", "geometry"]],
        how="left", distance_col="offset_distance_m",
    )
    joined = joined.rename(columns={"node_id": "nearest_node_id"})
    return joined.drop(columns=["index_right"], errors="ignore")
