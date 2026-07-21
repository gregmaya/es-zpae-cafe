import math

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from web_layer import build_address_label, build_search_index, join_address_labels, join_occupancy_context, reproject_competitor_locations, trim_candidate_properties


def test_build_address_label_normal_case():
    assert build_address_label("CALLE", "ARGANZUELA", "2") == "Calle Arganzuela, 2"


def test_build_address_label_omits_unknown_numero():
    # Real data contains numero == "Desconocido" as a placeholder for an
    # unknown house number (e.g. PLAZA COLON) -- must not print the
    # placeholder verbatim.
    assert build_address_label("PLAZA", "COLON", "Desconocido") == "Plaza Colon"


def test_build_address_label_handles_null_tvia():
    # tvia is null for a small number of real rows -- fall back to just
    # the street name.
    assert build_address_label(None, "GRAN VIA", "10") == "Gran Via, 10"


def test_build_address_label_null_tvia_and_unknown_numero():
    assert build_address_label(None, "GRAN VIA", "Desconocido") == "Gran Via"


def test_build_address_label_handles_nan_tvia_from_gpkg_read():
    # geopandas reads a missing tvia back from GPKG as float('nan'), not
    # None -- confirmed against real data (rt_portalpk_p_zpae_clip.gpkg
    # has exactly one such row). NaN is truthy in Python, so `if tvia:`
    # alone would try to call .title() on a float and crash.
    assert build_address_label(math.nan, "DESCONOCIDO", "3") == "Desconocido, 3"


def _results_gdf(id_porpks):
    return gpd.GeoDataFrame(
        {"id_porpk": id_porpks},
        geometry=[Point(0, 0) for _ in id_porpks],
        crs="EPSG:25830",
    )


def test_join_address_labels_attaches_label():
    results = _results_gdf([1, 2])
    portal = gpd.GeoDataFrame(
        {
            "id_porpk": [1, 2],
            "tvia": ["CALLE", "PLAZA"],
            "nombre": ["ARGANZUELA", "COLON"],
            "numero": ["2", "Desconocido"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:25830",
    )
    joined = join_address_labels(results, portal)
    labels = dict(zip(joined["id_porpk"], joined["address"]))
    assert labels[1] == "Calle Arganzuela, 2"
    assert labels[2] == "Plaza Colon"


def test_join_address_labels_left_join_keeps_unmatched_rows():
    results = _results_gdf([1, 99])  # 99 has no match in portal
    portal = gpd.GeoDataFrame(
        {"id_porpk": [1], "tvia": ["CALLE"], "nombre": ["ARGANZUELA"], "numero": ["2"]},
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_address_labels(results, portal)
    assert len(joined) == 2
    labels = dict(zip(joined["id_porpk"], joined["address"]))
    assert labels[1] == "Calle Arganzuela, 2"
    assert pd.isna(labels[99])


def test_join_occupancy_context_attaches_fields_and_parses_json():
    # Fixture mirrors real upstream dtype conventions: src/hosteleria.py's
    # summarize_candidate_context stores these boolean columns as
    # object-dtype-wrapped native Python bool (via .astype(object)) to
    # preserve `is True`/`is False` semantics against numpy.bool_. Using
    # pd.array(..., dtype=object) here (rather than a plain list, which
    # pandas would infer as numpy.bool_) lets this test's identity
    # assertions actually catch a regression that silently loses that
    # property during the join.
    results = _results_gdf([1])
    tagged = gpd.GeoDataFrame(
        {
            "id_porpk": [1],
            "has_commercial_local": pd.array([True], dtype=object),
            "current_activity_summary": ['[{"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}]'],
            "is_existing_hosteleria_class": pd.array([True], dtype=object),
        },
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_occupancy_context(results, tagged)
    row = joined.iloc[0]
    assert row["has_commercial_local"] is True
    assert row["is_existing_hosteleria_class"] is True
    assert row["current_activity_summary"] == [
        {"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}
    ]


def test_join_occupancy_context_sanitizes_nan_in_activity_summary():
    # Real data contains literal NaN tokens in this JSON string column
    # (e.g. id_seccion: NaN for ~1,481 of 13,876 real rows) -- json.loads
    # accepts bare NaN as an extension, but re-serializing it produces
    # invalid JSON, so it must be sanitized to None/null.
    results = _results_gdf([1])
    tagged = gpd.GeoDataFrame(
        {
            "id_porpk": [1],
            "has_commercial_local": pd.array([True], dtype=object),
            "current_activity_summary": ['[{"id_seccion": NaN, "desc_epigrafe": NaN, "desc_situacion_local": "Abierto"}]'],
            "is_existing_hosteleria_class": pd.array([True], dtype=object),
        },
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_occupancy_context(results, tagged)
    summary = joined.iloc[0]["current_activity_summary"]
    assert summary == [{"id_seccion": None, "desc_epigrafe": None, "desc_situacion_local": "Abierto"}]


def test_join_occupancy_context_coerces_string_booleans_from_gpkg():
    # GPKG has no native boolean type -- GDAL round-trips Python bool
    # columns as the literal strings "True"/"False", confirmed against
    # real data in candidate_addresses_zpae_tagged.gpkg.
    results = _results_gdf([1, 2])
    tagged = gpd.GeoDataFrame(
        {
            "id_porpk": [1, 2],
            "has_commercial_local": ["True", "False"],
            "current_activity_summary": ["[]", "[]"],
            "is_existing_hosteleria_class": ["False", "True"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:25830",
    )
    joined = join_occupancy_context(results, tagged)
    row0, row1 = joined.iloc[0], joined.iloc[1]
    assert row0["has_commercial_local"] is True
    assert row0["is_existing_hosteleria_class"] is False
    assert row1["has_commercial_local"] is False
    assert row1["is_existing_hosteleria_class"] is True


def test_reproject_competitor_locations_known_coordinate():
    # A known EPSG:25830 point in central Madrid; expected lon/lat computed
    # independently via pyproj.Transformer (verified against
    # EPSG:25830 -> EPSG:4326 for this exact input).
    gdf = _results_gdf([1])
    gdf["comp_x"] = [440000.0]
    gdf["comp_y"] = [4474000.0]
    lons, lats = reproject_competitor_locations(gdf, "comp_x", "comp_y", "EPSG:25830")
    assert math.isclose(lons[0], -3.7071991233876656, abs_tol=1e-4)
    assert math.isclose(lats[0], 40.41446049371108, abs_tol=1e-4)


def test_reproject_competitor_locations_passes_through_none():
    gdf = _results_gdf([1, 2])
    gdf["comp_x"] = [440000.0, None]
    gdf["comp_y"] = [4474000.0, None]
    lons, lats = reproject_competitor_locations(gdf, "comp_x", "comp_y", "EPSG:25830")
    assert lons[1] is None
    assert lats[1] is None
    assert lons[0] is not None


def test_trim_candidate_properties_drops_redundant_xy_columns():
    properties = {
        "id_porpk": 1,
        "address": "Calle Arganzuela, 2",
        "strict_pass": True,
        "strict_nearest_binding_x": 440000.0,
        "strict_nearest_binding_y": 4474000.0,
        "strict_nearest_binding_lon": -3.71,
        "strict_nearest_binding_lat": 40.41,
        "lenient_nearest_binding_x": 440001.0,
        "lenient_nearest_binding_y": 4474001.0,
        "strict_nearest_overall_x": 440002.0,
        "strict_nearest_overall_y": 4474002.0,
        "lenient_nearest_overall_x": 440003.0,
        "lenient_nearest_overall_y": 4474003.0,
    }
    trimmed = trim_candidate_properties(properties)
    assert trimmed == {
        "id_porpk": 1,
        "address": "Calle Arganzuela, 2",
        "strict_pass": True,
        "strict_nearest_binding_lon": -3.71,
        "strict_nearest_binding_lat": 40.41,
    }


def test_trim_candidate_properties_missing_columns_is_a_noop():
    # Not every row has every competitor column populated (e.g. a null
    # binding lookup on a prohibited-outright address) -- must not raise
    # if an x/y key is simply absent from this particular properties dict.
    properties = {"id_porpk": 1, "address": "Plaza Colon"}
    assert trim_candidate_properties(properties) == properties


def test_build_search_index_extracts_id_address_lon_lat():
    gdf = gpd.GeoDataFrame(
        {"id_porpk": [1, 2], "address": ["Calle Arganzuela, 2", "Plaza Colon"]},
        geometry=[Point(-3.71, 40.41), Point(-3.70, 40.42)],
        crs="EPSG:4326",
    )
    index = build_search_index(gdf)
    assert index == [
        {"id_porpk": 1, "address": "Calle Arganzuela, 2", "lon": -3.71, "lat": 40.41},
        {"id_porpk": 2, "address": "Plaza Colon", "lon": -3.70, "lat": 40.42},
    ]


def test_build_search_index_handles_null_address():
    # join_address_labels is a left join -- a row with no portal match
    # keeps a null address rather than being dropped (see Stage 5).
    gdf = gpd.GeoDataFrame(
        {"id_porpk": [1], "address": [None]},
        geometry=[Point(-3.71, 40.41)],
        crs="EPSG:4326",
    )
    index = build_search_index(gdf)
    assert index == [{"id_porpk": 1, "address": None, "lon": -3.71, "lat": 40.41}]
