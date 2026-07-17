from hosteleria import build_competitor_layer


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
