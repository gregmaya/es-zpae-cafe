import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from web_layer import build_address_label, join_address_labels, join_occupancy_context


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
