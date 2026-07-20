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
    results = _results_gdf([1])
    tagged = gpd.GeoDataFrame(
        {
            "id_porpk": [1],
            "has_commercial_local": [True],
            "current_activity_summary": ['[{"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}]'],
            "is_existing_hosteleria_class": [True],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_occupancy_context(results, tagged)
    row = joined.iloc[0]
    assert row["has_commercial_local"] == True
    assert row["is_existing_hosteleria_class"] == True
    assert row["current_activity_summary"] == [
        {"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}
    ]
