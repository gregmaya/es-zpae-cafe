import geopandas as gpd
from shapely.geometry import Point

from hosteleria import build_competitor_layer, join_candidate_context, summarize_candidate_context


def _record(id_local, id_seccion, id_epigrafe, desc_epigrafe, desc_situacion_local,
            rotulo, x, y):
    return {
        "id_local": id_local,
        "id_seccion": id_seccion,
        "id_epigrafe": id_epigrafe,
        "desc_epigrafe": desc_epigrafe,
        "desc_situacion_local": desc_situacion_local,
        "rotulo": rotulo,
        "coordenada_x_local": x,
        "coordenada_y_local": y,
    }


def test_build_competitor_layer_filters_and_classifies():
    records = [
        _record("1", "I", "561001", "RESTAURANTE", "Abierto",
                "CASA PEPE", "440000.0", "4475000.0"),
        _record("2", "I", "563006", "CIBER-CAFE", "Abierto",
                "CIBER XYZ", "440100.0", "4475100.0"),
        _record("3", "I", "561001", "RESTAURANTE", "Cerrado",
                "CLOSED PLACE", "440200.0", "4475200.0"),
        _record("4", "R", "999999", "UNKNOWN ACTIVITY", "Abierto",
                "MYSTERY VENUE", "440300.0", "4475300.0"),
        _record("5", "G", "471101", "COMERCIO", "Abierto",
                "SHOP", "440400.0", "4475400.0"),
    ]

    result = build_competitor_layer(records)

    assert result.mapped_count == 1
    assert result.excluded_count == 1
    assert result.unmapped_count == 1
    assert result.unmapped_epigrafes == {("999999", "UNKNOWN ACTIVITY")}
    assert len(result.gdf) == 1
    assert result.gdf.iloc[0]["decreto_class"] == "clase_v_cat10"
    assert result.gdf.iloc[0]["id_local"] == "1"
    assert result.gdf.crs.to_string() == "EPSG:25830"


def test_build_competitor_layer_empty_input():
    result = build_competitor_layer([])
    assert result.mapped_count == 0
    assert len(result.gdf) == 0


def _locals_gdf():
    return gpd.GeoDataFrame(
        {
            "id_local": ["L1"],
            "id_seccion": ["I"],
            "id_epigrafe": ["561001"],
            "desc_epigrafe": ["RESTAURANTE"],
            "desc_situacion_local": ["Abierto"],
        },
        geometry=[Point(5, 5)],
        crs="EPSG:25830",
    )


def _addresses_gdf():
    return gpd.GeoDataFrame(
        {"id_porpk": ["a1", "a2"]},
        geometry=[Point(0, 0), Point(1000, 1000)],
        crs="EPSG:25830",
    )


def test_join_candidate_context_keeps_unmatched_addresses():
    joined = join_candidate_context(_addresses_gdf(), _locals_gdf(), tolerance_m=15)

    a1_rows = joined[joined["id_porpk"] == "a1"]
    a2_rows = joined[joined["id_porpk"] == "a2"]

    assert (a1_rows["id_local"] == "L1").all()
    assert a2_rows["id_local"].isna().all()


def test_summarize_candidate_context():
    joined = join_candidate_context(_addresses_gdf(), _locals_gdf(), tolerance_m=15)

    summary = summarize_candidate_context(joined, address_id_col="id_porpk")

    a1 = summary[summary["id_porpk"] == "a1"].iloc[0]
    a2 = summary[summary["id_porpk"] == "a2"].iloc[0]

    assert a1["has_commercial_local"] is True
    assert a1["is_existing_hosteleria_class"] is True
    assert a1["current_activity_summary"] == [
        {
            "id_seccion": "I",
            "desc_epigrafe": "RESTAURANTE",
            "desc_situacion_local": "Abierto",
        }
    ]

    assert a2["has_commercial_local"] is False
    assert a2["current_activity_summary"] == []
    assert a2["is_existing_hosteleria_class"] is False
