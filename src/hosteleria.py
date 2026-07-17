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


def join_candidate_context(
    addresses: gpd.GeoDataFrame,
    locals_gdf: gpd.GeoDataFrame,
    tolerance_m: float,
) -> gpd.GeoDataFrame:
    """Nearest-join every candidate address point to the closest local(s)
    in locals_gdf within tolerance_m. Addresses with no local within
    tolerance keep all their own columns with null local-side fields
    (standard left-join semantics), rather than being dropped."""
    return gpd.sjoin_nearest(
        addresses,
        locals_gdf,
        how="left",
        max_distance=tolerance_m,
        distance_col="match_distance_m",
    )


def summarize_candidate_context(
    joined: gpd.GeoDataFrame, address_id_col: str
) -> gpd.GeoDataFrame:
    """Collapse the (possibly multiple-rows-per-address) nearest-join
    result down to one row per address, summarizing whether a commercial
    local exists nearby and what it currently does."""
    summaries = []
    for address_id, group in joined.groupby(address_id_col, dropna=False):
        matched = group[group["id_local"].notna()]
        activity_summary = [
            {
                "id_seccion": row["id_seccion"],
                "desc_epigrafe": row["desc_epigrafe"],
                "desc_situacion_local": row["desc_situacion_local"],
            }
            for _, row in matched.iterrows()
        ]
        is_existing_hosteleria = any(
            classify_epigrafe(row["id_seccion"], row["id_epigrafe"]).status == "mapped"
            for _, row in matched.iterrows()
        )
        summaries.append(
            {
                address_id_col: address_id,
                "geometry": group.iloc[0]["geometry"],
                "has_commercial_local": len(matched) > 0,
                "current_activity_summary": activity_summary,
                "is_existing_hosteleria_class": is_existing_hosteleria,
            }
        )
    result = gpd.GeoDataFrame(summaries, geometry="geometry", crs=joined.crs)
    # Keep these as native Python bool objects rather than letting pandas
    # infer a numpy bool dtype column: numpy.bool_ scalars fail `is True`/
    # `is False` identity checks even though they compare equal.
    result["has_commercial_local"] = result["has_commercial_local"].astype(object)
    result["is_existing_hosteleria_class"] = result["is_existing_hosteleria_class"].astype(object)
    return result
