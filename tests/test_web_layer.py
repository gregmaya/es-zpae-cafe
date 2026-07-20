from web_layer import build_address_label


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
