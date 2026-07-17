"""
Maps censo de locales activity epígrafes (CNAE-based, from CKAN resource
200085-5-censo-locales on datos.madrid.es) to the Decreto 184/1998
class/categoría scheme used by every ZPAE zone's Normativa (see
src/zones.py and docs/data_sources.md for how the two relate).

Only seccion I (Hostelería) and R (Actividades artísticas, recreativas y
de entretenimiento) contain ZPAE-relevant epígrafes -- everything else is
"not_applicable". Confirmed against the live API 2026-07-18; see
docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md
for the full mapping table. Two documented gaps are deliberately left
unmapped/excluded rather than guessed, not silently absent:
  - Clase III Cat.2 ("salas de conciertos" / live theatre): 900003
    (theatre/live performance) is excluded rather than guessed.
  - Hotel bars/restaurants with direct street access (a subset of the
    551xxx accommodation epígrafes, excluded below as accommodation):
    the census doesn't tag street-access separately from other hotel
    amenities, so this edge case can't be distinguished from ordinary
    hotel accommodation with the data available.
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

    # Accommodation -- separate activity type, not gated by ZPAE hostelería/ocio rules
    "551001",  # HOTELES Y MOTELES CON RESTAURANTE
    "551002",  # HOTELES Y MOTELES SIN RESTAURANTE
    "551003",  # HOSTALES
    "551004",  # APART-HOTELES
    "551005",  # VIVIENDAS TURISTICAS
    "552001",  # ALBERGUES JUVENILES Y OTROS ALOJAMIENTOS TURISTICOS DE CORTA ESTANCIA
    "559001",  # COLEGIOS MAYORES Y RESIDENCIAS DE ESTUDIANTES
    "559002",  # PENSIONES
    "559003",  # CASAS DE HUESPEDES

    # Recreation/culture/sport -- no plausible reading under Decreto 184/1998 Clase III/IV/V-9/V-10
    "900001",  # ACTIVIDADES DE CREACION, ARTISTICAS Y ESPECTACULOS -- too broad/ambiguous, excluded rather than guessed
    "900002",  # LOCALES DE EXHIBICIONES EROTICAS -- only 1 open record, excluded rather than guessed
    "900003",  # TEATRO Y ACTIVIDADES ESCENICAS REALIZADAS EN DIRECTO -- plausible Clase III fit but excluded; Clase III Cat.2 remains documented gap
    "910001",  # ACTIVIDADES DE BIBLIOTECAS, ARCHIVOS, MUSEOS Y DE GALERIAS Y SALAS DE EXPOSICIONES SIN VENTA
    "910002",  # PARQUES ZOOLOGICOS, JARDINES BOTANICOS Y RESERVAS NATURALES
    "920001",  # JUEGOS DE AZAR Y APUESTAS DE GESTION PUBLICA O AUTORIZACION ESPECIAL (ESTADO Y ONCE)
    "920002",  # JUEGOS DE AZAR Y APUESTAS DE GESTION PRIVADA (BINGOS, CASINOS, MAQUINAS TRAGAPERRAS)
    "931001",  # GESTION DE INSTALACIONES DEPORTIVAS
    "931002",  # PISCINAS DE USO PUBLICO DE TEMPORADA
    "931003",  # PISCINAS DE USO PUBLICO CLIMATIZADAS
    "931004",  # PISCINAS PUBLICAS CLIMATIZADAS/TEMPORADA
    "931005",  # PISCINA PRIVADA DE TEMPORADA
    "931008",  # ACTIVIDADES DE LOS GIMNASIOS
    "931009",  # ACTIVIDADES DE CLUBES DEPORTIVOS Y OTRAS ACTIVIDADES DEPORTIVAS
    "931010",  # PISCINAS DE COMUNIDADES DE VECINOS DE TEMPORADA
    "931011",  # PISCINAS DE COMUNIDADES DE VECINOS CLIMATIZADAS
    "931012",  # ESTABLECIMIENTOS DE EQUITACION
    "932001",  # CENTROS DE JUEGOS O CELEBRACIONES INFANTILES CON COCINA
    "932002",  # CENTROS DE JUEGOS O CELEBRACIONES INFANTILES SIN COCINA
    "932007",  # SALONES DE RECREO Y DIVERSION Y OTRAS ACTIVIDADES RECREATIVAS
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
