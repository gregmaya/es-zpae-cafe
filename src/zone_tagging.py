"""
Tags candidate/competitor points with their ZPAE zone (point-in-polygon
against zpae_ambitos.geojson) and street classification (nearest-line
match against zpae_clasificacion.geojson, normalized to the same
alta/moderada/baja/sin_superacion keys used in src/zones.py). See
docs/superpowers/specs/2026-07-19-stage4-distance-engine-design.md.
"""

import geopandas as gpd

MAX_CLASSIFICATION_DISTANCE_M = 30

# Normalizes zpae_clasificacion.geojson's Spanish "Clasifica" text to the
# same snake_case keys used in src/zones.py's ClassificationRule dicts.
CLASIFICA_TO_KEY = {
    "Alta": "alta",
    "Moderada": "moderada",
    "Baja": "baja",
    "Sin superación de objetivos por ocio": "sin_superacion",
}

# Art. 6 of every zone's Normativa: when an activity has public access on
# streets of different classification, the applicable regime is the most
# restrictive one. Used to break ties when a point is equidistant to two
# differently-classified street segments -- and, as a side effect,
# resolves a real Stage 2 data-quality issue where some competitors have
# multiple identical rows in the source census data (see
# docs/data_sources.md). Lower rank = more restrictive = kept.
_RESTRICTIVENESS_RANK = {"alta": 0, "moderada": 1, "baja": 2, "sin_superacion": 3}


def tag_zone_membership(
    points_gdf: gpd.GeoDataFrame, ambitos_gdf: gpd.GeoDataFrame, id_col: str
) -> gpd.GeoDataFrame:
    """Tag each point with the ZPAE zone it falls inside (ambitos_gdf's
    'ZPAE' column, matching src/zones.py's ZpaeZone.name spelling), or
    NaN if it's outside all four zone polygons -- e.g. in Stage 1's 300m
    buffer margin, where no ZPAE distance rule applies at all."""
    joined = gpd.sjoin(
        points_gdf, ambitos_gdf[["ZPAE", "geometry"]],
        how="left", predicate="within",
    )
    joined = joined.drop_duplicates(subset=id_col, keep="first")
    joined = joined.rename(columns={"ZPAE": "zpae_zone"})
    return joined.drop(columns=["index_right"], errors="ignore")


def tag_street_classification(
    points_gdf: gpd.GeoDataFrame,
    clasificacion_gdf: gpd.GeoDataFrame,
    id_col: str,
    max_distance_m: float = MAX_CLASSIFICATION_DISTANCE_M,
) -> gpd.GeoDataFrame:
    """Tag each point with the classification of its nearest classified
    street segment, normalized to alta/moderada/baja/sin_superacion, or
    NaN beyond max_distance_m. Confirmed against real data that
    zone-interior points are almost always within a few metres of a
    classified street (median 4.2m in the real candidate dataset), so
    30m is a generous cutoff, not a tight one.

    sjoin_nearest can return more than one row per input point when
    multiple lines are equidistant, or when the input itself already has
    duplicate rows for the same id. Both cases are resolved the same
    way: keep the most restrictive classification (Art. 6)."""
    joined = gpd.sjoin_nearest(
        points_gdf, clasificacion_gdf[["Clasifica", "geometry"]],
        how="left", max_distance=max_distance_m,
        distance_col="dist_to_classified_street",
    )
    joined["classification"] = joined["Clasifica"].map(CLASIFICA_TO_KEY)
    joined["_rank"] = joined["classification"].map(_RESTRICTIVENESS_RANK)
    joined = joined.sort_values("_rank", na_position="last")
    joined = joined.drop_duplicates(subset=id_col, keep="first")
    return joined.drop(columns=["Clasifica", "_rank", "index_right"], errors="ignore")
