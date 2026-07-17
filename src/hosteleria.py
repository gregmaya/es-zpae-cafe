"""
Builds the two Stage 2 outputs from the raw censo de locales pull:
(A) the hostelería/ocio competitor point layer, and (B) commercial-local
context joined onto every candidate address point. See
docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md.
"""

from dataclasses import dataclass, field

import geopandas as gpd
from shapely.geometry import Point

from activities import classify_epigrafe

TARGET_CRS = "EPSG:25830"


@dataclass
class CompetitorBuildResult:
    gdf: gpd.GeoDataFrame
    mapped_count: int
    excluded_count: int
    unmapped_count: int
    unmapped_epigrafes: set = field(default_factory=set)


def build_competitor_layer(records: list[dict]) -> CompetitorBuildResult:
    """Filter raw censo de locales records to active seccion I/R rows,
    classify each against the Decreto 184/1998 scheme, and build the
    competitor point GeoDataFrame. Excluded/unmapped rows are dropped
    but counted, not silently discarded."""
    mapped_rows = []
    mapped_count = 0
    excluded_count = 0
    unmapped_count = 0
    unmapped_epigrafes = set()

    for row in records:
        if row["id_seccion"] not in ("I", "R"):
            continue
        if row["desc_situacion_local"] != "Abierto":
            continue

        result = classify_epigrafe(row["id_seccion"], row["id_epigrafe"])
        if result.status == "mapped":
            mapped_count += 1
            mapped_rows.append(
                {
                    "id_local": row["id_local"],
                    "rotulo": row["rotulo"],
                    "decreto_class": result.decreto_class,
                    "desc_epigrafe": row["desc_epigrafe"],
                    "geometry": Point(
                        float(row["coordenada_x_local"]),
                        float(row["coordenada_y_local"]),
                    ),
                }
            )
        elif result.status == "excluded":
            excluded_count += 1
        elif result.status == "unmapped":
            unmapped_count += 1
            unmapped_epigrafes.add((row["id_epigrafe"], row["desc_epigrafe"]))

    if mapped_rows:
        gdf = gpd.GeoDataFrame(mapped_rows, geometry="geometry", crs=TARGET_CRS)
    else:
        gdf = gpd.GeoDataFrame(columns=["id_local", "rotulo", "decreto_class", "desc_epigrafe", "geometry"], crs=TARGET_CRS)
        gdf = gdf.set_geometry("geometry")

    return CompetitorBuildResult(
        gdf=gdf,
        mapped_count=mapped_count,
        excluded_count=excluded_count,
        unmapped_count=unmapped_count,
        unmapped_epigrafes=unmapped_epigrafes,
    )
