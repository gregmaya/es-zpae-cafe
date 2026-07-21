"""
Stage 6: reproject the two raw zoning-rule source layers (zone boundaries
and street noise classifications) to EPSG:4326 for the web app's
regulatory overlay. See
docs/superpowers/specs/2026-07-20-stage6-web-app-design.md.

Run locally:
    python scripts/10_build_regulatory_layer.py
"""

from pathlib import Path

import geopandas as gpd

RAW_ZPAE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "zpae"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"

WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

zones = gpd.read_file(RAW_ZPAE_DIR / "zpae_ambitos.geojson")
assert zones.crs is not None and zones.crs.to_epsg() == 25830, (
    f"Expected zpae_ambitos.geojson in EPSG:25830, got {zones.crs}"
)
zones = zones.to_crs("EPSG:4326")
zones.to_file(WEB_DATA_DIR / "zpae_zones.geojson", driver="GeoJSON")
print(f"Saved {len(zones)} zone polygons to {WEB_DATA_DIR / 'zpae_zones.geojson'}")

streets = gpd.read_file(RAW_ZPAE_DIR / "zpae_clasificacion.geojson")
assert streets.crs is not None and streets.crs.to_epsg() == 25830, (
    f"Expected zpae_clasificacion.geojson in EPSG:25830, got {streets.crs}"
)
streets = streets.to_crs("EPSG:4326")
streets.to_file(WEB_DATA_DIR / "zpae_streets.geojson", driver="GeoJSON")
print(f"Saved {len(streets)} street segments to {WEB_DATA_DIR / 'zpae_streets.geojson'}")
