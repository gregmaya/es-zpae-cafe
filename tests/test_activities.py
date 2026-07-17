from activities import EpigrafeClassification, classify_epigrafe


def test_mapped_hosteleria_epigrafe():
    result = classify_epigrafe("I", "561001")  # RESTAURANTE
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_v_cat10")


def test_mapped_discoteca_epigrafe():
    result = classify_epigrafe("R", "932006")  # DISCOTECAS Y SALAS DE BAILE
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_iv_cat4")


def test_mapped_bar_especial_epigrafe():
    result = classify_epigrafe("I", "563003")  # BAR ESPECIAL CON ACTUACIONES
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_v_cat9")


def test_mapped_cafe_espectaculo_epigrafe():
    result = classify_epigrafe("I", "563007")  # CAFE ESPECTACULO
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_iii_cat1")


def test_excluded_epigrafe():
    result = classify_epigrafe("I", "563006")  # CIBER-CAFE
    assert result == EpigrafeClassification(status="excluded")


def test_excluded_institutional_catering_epigrafe():
    result = classify_epigrafe("I", "562902")  # SERVICIOS DE COMEDOR EN CENTROS EDUCATIVOS
    assert result == EpigrafeClassification(status="excluded")


def test_unmapped_epigrafe_in_relevant_seccion():
    # simulates a real gap: a seccion I/R code not in our mapping table
    result = classify_epigrafe("I", "999999")
    assert result == EpigrafeClassification(status="unmapped")


def test_not_applicable_outside_seccion_i_r():
    result = classify_epigrafe("G", "471101")  # retail, unrelated seccion
    assert result == EpigrafeClassification(status="not_applicable")


def test_excluded_accommodation_hotel_epigrafe():
    # Accommodation block: hotels are not gated by ZPAE hostelería rules
    result = classify_epigrafe("I", "551001")  # HOTELES Y MOTELES CON RESTAURANTE
    assert result == EpigrafeClassification(status="excluded")


def test_excluded_sports_gym_epigrafe():
    # Recreation/sport block: gyms/sports facilities excluded
    result = classify_epigrafe("R", "931008")  # ACTIVIDADES DE LOS GIMNASIOS
    assert result == EpigrafeClassification(status="excluded")


def test_excluded_theatre_epigrafe():
    # Recreation/culture block: theatre deliberately excluded (Clase III Cat.2 gap)
    result = classify_epigrafe("R", "900003")  # TEATRO Y ACTIVIDADES ESCENICAS REALIZADAS EN DIRECTO
    assert result == EpigrafeClassification(status="excluded")
