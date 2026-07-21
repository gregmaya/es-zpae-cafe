"""
Assembles Stage 5's static web layer: joins Stage 4's pass/fail +
competitor-identity results with a human-readable address label (from
Stage 2's raw portal-point pull) and today's occupancy context (from
Stage 2/7's tagged candidate addresses), then reprojects everything to
EPSG:4326 for the web. See
docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md.
"""

import json
import math

import geopandas as gpd
from pyproj import Transformer


def build_address_label(tvia: str | None, nombre: str, numero: str) -> str:
    """Build a human-readable address label, e.g.
    ("CALLE", "ARGANZUELA", "2") -> "Calle Arganzuela, 2". numero ==
    "Desconocido" (a real placeholder in the source data for an unknown
    house number) is omitted rather than printed verbatim. A null tvia
    (present for a small number of real rows) falls back to just the
    street name. A missing tvia read back from GPKG via geopandas comes
    through as float('nan'), not None -- confirmed against real data --
    and NaN is truthy in Python, so it must be checked explicitly rather
    than relying on `if tvia:` alone."""
    if isinstance(tvia, float) and math.isnan(tvia):
        tvia = None
    street = nombre.title()
    if tvia:
        street = f"{tvia.title()} {street}"
    if numero and numero != "Desconocido":
        return f"{street}, {numero}"
    return street


def join_address_labels(
    results_gdf: gpd.GeoDataFrame, portal_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Left-join results_gdf to portal_gdf on id_porpk, adding an
    'address' column. Rows with no match keep their other columns with a
    null address rather than being dropped."""
    labels = portal_gdf[["id_porpk", "tvia", "nombre", "numero"]].copy()
    labels["address"] = labels.apply(
        lambda row: build_address_label(row["tvia"], row["nombre"], row["numero"]), axis=1,
    )
    return results_gdf.merge(labels[["id_porpk", "address"]], on="id_porpk", how="left")


def _to_bool(value):
    """Coerce a boolean-ish value to a real Python bool. GPKG has no
    native boolean column type, so GDAL round-trips Python bool columns
    (stored as object-dtype by src/hosteleria.py's
    summarize_candidate_context) as the literal strings "True"/"False"
    on read via geopandas.read_file(). Handles that case, an already-real
    bool, and anything else pandas might hand back."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value == "True"
    return bool(value)


def _replace_nan_with_none(value):
    """Recursively replace float NaN with None in a parsed JSON structure,
    so it can be safely re-serialized as valid JSON (bare NaN is not valid
    JSON syntax, but json.loads accepts it as an extension -- confirmed
    present in real current_activity_summary data, e.g. id_seccion: NaN
    for some records)."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _replace_nan_with_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_nan_with_none(v) for v in value]
    return value


def join_occupancy_context(
    results_gdf: gpd.GeoDataFrame, tagged_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Left-join results_gdf to tagged_gdf on id_porpk, adding
    has_commercial_local, current_activity_summary (parsed from its GPKG
    JSON-string form into a real list-of-dicts), and
    is_existing_hosteleria_class."""
    context = tagged_gdf[[
        "id_porpk", "has_commercial_local", "current_activity_summary",
        "is_existing_hosteleria_class",
    ]].copy()
    context["current_activity_summary"] = context["current_activity_summary"].apply(
        lambda value: _replace_nan_with_none(json.loads(value)) if isinstance(value, str) else value
    )
    # Force object dtype on the result: Series.apply()/merge() would
    # otherwise infer a specialized numpy bool dtype, which hands back
    # numpy.bool_ scalars that fail `is True`/`is False` identity checks
    # (see src/hosteleria.py's summarize_candidate_context for the same
    # concern upstream).
    context["has_commercial_local"] = context["has_commercial_local"].apply(_to_bool).astype(
        object
    )
    context["is_existing_hosteleria_class"] = (
        context["is_existing_hosteleria_class"].apply(_to_bool).astype(object)
    )
    return results_gdf.merge(context, on="id_porpk", how="left")


def reproject_competitor_locations(
    gdf: gpd.GeoDataFrame, x_col: str, y_col: str, source_crs: str
) -> tuple[list, list]:
    """Reproject a competitor-location x/y column pair (plain floats, not
    GeoDataFrame geometry -- e.g. the nearest-competitor lookup columns
    from Stage 4) from source_crs to EPSG:4326. Returns (lons, lats),
    same order as gdf. None/NaN input coordinates pass through as None
    rather than being reprojected."""
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    lons, lats = [], []
    for x, y in zip(gdf[x_col], gdf[y_col]):
        if x is None or y is None or (isinstance(x, float) and math.isnan(x)):
            lons.append(None)
            lats.append(None)
            continue
        lon, lat = transformer.transform(x, y)
        lons.append(lon)
        lats.append(lat)
    return lons, lats


_REDUNDANT_COMPETITOR_XY_COLUMNS = [
    f"{prefix}_{axis}"
    for prefix in (
        "strict_nearest_binding", "lenient_nearest_binding",
        "strict_nearest_overall", "lenient_nearest_overall",
    )
    for axis in ("x", "y")
]


def trim_candidate_properties(properties: dict) -> dict:
    """Drop the EPSG:25830 x/y competitor-location columns now redundant
    with their _lon/_lat companions (added by Stage 5's
    reproject_competitor_locations), returning the trimmed property dict
    used for the web tileset."""
    return {
        key: value for key, value in properties.items()
        if key not in _REDUNDANT_COMPETITOR_XY_COLUMNS
    }
