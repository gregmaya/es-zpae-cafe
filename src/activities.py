"""
Maps censo de locales activity epígrafes (CNAE-based, from CKAN resource
200085-5-censo-locales on datos.madrid.es) to the Decreto 184/1998
class/categoría scheme used by every ZPAE zone's Normativa (see
src/zones.py and docs/data_sources.md for how the two relate).

Only seccion I (Hostelería) and R (Actividades artísticas, recreativas y
de entretenimiento) contain ZPAE-relevant epígrafes -- everything else is
"not_applicable". Confirmed against the live API 2026-07-17; see
docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md
for the full mapping table and the two documented gaps (Clase III Cat.2
"salas de conciertos", and hotel bars/restaurants with direct street
access) that are deliberately left unmapped rather than guessed.
"""

from dataclasses import dataclass

RELEVANT_SECCIONES = {"I", "R"}

EPIGRAFE_TO_DECRETO_CLASS = {
    # Clase III Cat.1 -- esparcimiento y diversión
    "563007": "clase_iii_cat1",  # CAFE ESPECTACULO
    "932004": "clase_iii_cat1",  # SALAS DE FIESTA CON RESTAURACION
    "932005": "clase_iii_cat1",  # SALAS DE FIESTA SIN RESTAURACION
    # Clase IV Cat.4 -- de baile
    "932006": "clase_iv_cat4",   # DISCOTECAS Y SALAS DE BAILE
    # Clase V Cat.9 -- ocio y diversión
    "563002": "clase_v_cat9",    # BAR ESPECIAL SIN ACTUACIONES
    "563003": "clase_v_cat9",    # BAR ESPECIAL CON ACTUACIONES
    # Clase V Cat.10 -- hostelería y restauración
    "561001": "clase_v_cat10",   # RESTAURANTE
    "561002": "clase_v_cat10",   # RESTAURANTES DE COMIDA RAPIDA
    "561003": "clase_v_cat10",   # AUTOSERVICIO DE RESTAURACION
    "561004": "clase_v_cat10",   # BAR RESTAURANTE
    "561005": "clase_v_cat10",   # BAR CON COCINA
    "561006": "clase_v_cat10",   # CAFETERIA
    "561007": "clase_v_cat10",   # CHOCOLATERIA/SALON DE TE Y HELADERIA
    "563001": "clase_v_cat10",   # BODEGA CON CONSUMO
    "563004": "clase_v_cat10",   # TABERNA
    "563005": "clase_v_cat10",   # BAR SIN COCINA
    "562101": "clase_v_cat10",   # SALONES DE BANQUETES
}

# Present in seccion I/R but deliberately NOT gated by the ZPAE
# hostelería/ocio rules -- see design doc for the reasoning behind each.
EXCLUDED_EPIGRAFES = {
    "561008",  # VENDEDOR AMBULANTE / RESTAURACION MOVIL -- no fixed premises
    "562901",  # COMIDAS EN INSTALACIONES DEPORTIVAS, OFICINAS -- not open to the public
    "562902",  # COMEDOR EN CENTROS EDUCATIVOS/CUIDADO INFANTIL -- not open to the public
    "562903",  # COMEDOR EN CENTROS PARA MAYORES -- not open to the public
    "562904",  # COMEDOR EN CENTROS DE SERVICIOS SOCIALES -- not open to the public
    "562905",  # PREPARACION DE COMIDAS EN HOSPITALES -- not open to the public
    "563006",  # CIBER-CAFE
}


@dataclass(frozen=True)
class EpigrafeClassification:
    status: str  # "mapped" | "excluded" | "unmapped" | "not_applicable"
    decreto_class: str | None = None


def classify_epigrafe(id_seccion: str, id_epigrafe: str) -> EpigrafeClassification:
    """Classify a censo de locales epígrafe against the Decreto 184/1998
    scheme. Only seccion I/R are ZPAE-relevant; anything else is
    "not_applicable" without consulting the mapping tables."""
    if id_seccion not in RELEVANT_SECCIONES:
        return EpigrafeClassification(status="not_applicable")
    if id_epigrafe in EXCLUDED_EPIGRAFES:
        return EpigrafeClassification(status="excluded")
    if id_epigrafe in EPIGRAFE_TO_DECRETO_CLASS:
        return EpigrafeClassification(
            status="mapped",
            decreto_class=EPIGRAFE_TO_DECRETO_CLASS[id_epigrafe],
        )
    return EpigrafeClassification(status="unmapped")
