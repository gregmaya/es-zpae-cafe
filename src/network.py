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
