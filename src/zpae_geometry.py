"""
Shared ZPAE study-area geometry helper, used by both the network clip
(scripts/02_clip_network_to_zpae.py) and the hostelería reconcile
pipeline (scripts/04_reconcile_hosteleria.py) so the dissolve+buffer
logic lives in one place instead of being copy-pasted.
"""

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

TARGET_CRS = "EPSG:25830"  # ETRS89 / UTM 30N, metres


def build_study_area(zpae_ambitos: gpd.GeoDataFrame, buffer_m: float) -> BaseGeometry:
    """Dissolve the ZPAE zone boundary polygons into one buffered study-area
    geometry, reprojecting to TARGET_CRS first if the input isn't already
    in it."""
    if zpae_ambitos.crs is None:
        zpae_ambitos = zpae_ambitos.set_crs(TARGET_CRS)
    else:
        zpae_ambitos = zpae_ambitos.to_crs(TARGET_CRS)
    return zpae_ambitos.dissolve().buffer(buffer_m).iloc[0]
