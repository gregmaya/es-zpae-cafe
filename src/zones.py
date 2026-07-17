"""
Canonical list of ZPAE zones in scope for this project, plus the parsed
distance-threshold rule per zone.

No layer in the ZPAE GIS dataset carries a numeric metre threshold anywhere
(confirmed in Stage 1; see docs/data_sources.md). The real numbers come from
each zone's "Normativa del Plan Zonal Específico" PDF -- the `Enlace`
landing pages 403 scripted fetches, so these were retrieved manually. Of
the ~5 PDFs published per zone (acuerdo de aprobación, análisis de
viabilidad, estudio, plano de delimitación, normativa), only the
**Normativa del Plan Zonal Específico** one carries the operative rule --
the rest are supporting studies/maps, not needed for thresholds. Some
zones (AZCA, Gaztambide) also had a 2022 "modificación" published
separately in the BOAM -- see per-zone notes below for whether it changed
numeric thresholds or only street delimitation tables.

All PDFs are archived in docs/normativa_pdfs/.

`name` matches the spelling used in zpae_ambitos.geojson (ZPAE.shp);
`clasificacion_name` matches the differently-spelled ZPAE field in
zpae_clasificacion.geojson (ZPAE_clasificacion.shp) -- the two source
shapefiles don't agree on zone-name text, so both are recorded here rather
than joining on a single name string.

## Rule shape (confirmed across all four zones' Normativa PDFs)

This is NOT a flat "classification -> metres" lookup. The threshold for a
candidate address depends on BOTH:
  1. the classification of the street segment the candidate is on (its own
     access point), which determines the applicable regime (Art. 6 in every
     zone: "el régimen normativo ... vendrá determinado por el grado de
     contaminación del tramo de la calle donde se encuentre el acceso para
     el público" -- this is also why ZPAE_clasificacion.shp being a
     per-street LINE layer, not a polygon layer, is the right data model);
     and
  2. the classification of the street segment the nearest EXISTING
     hostelería is on -- the required distance is NOT symmetric (e.g. in
     Trafalgar-Ríos Rosas, a Baja-zone candidate needs 150m from an
     Alta-zone competitor, but a Moderada-zone candidate only needs 100m
     from the same competitor).

Measurement method (confirmed explicitly in every zone's PDF): minimum
distance measured in a straight line along the axis of streets or public
spaces, door to door -- i.e. network distance along the street graph, not
euclidean. This is the basis for using Cityseer.

`ClassificationRule.prohibited_outright=True` means no new licence at all,
regardless of distance. `prohibited_with_music=True` means banned only for
the "con música" / live-music-amenity variant of the activity -- the plain
hostelería/no-music case (what this project models) falls through to
`min_distance_m`. A key ABSENT from `min_distance_m` means that existing
competitor classification triggers no restriction (e.g. most zones don't
mention "sin_superacion" competitors at all -- only Centro does).
`rules` has no entry for a classification a zone doesn't have at all (e.g.
AZCA has no "alta" streets and no "sin_superacion" chapter -- confirmed by
zpae_clasificacion.shp only ever showing Baja/Moderada for that zone).

## Rule shape differs meaningfully per zone -- don't assume Trafalgar's
   shape generalizes:
  - Centro and Gaztambide ban Alta outright for ALL hostelería (no
    music-only carve-out). AZCA's Alta... doesn't exist; AZCA has no Alta
    chapter at all.
  - AZCA's Moderada/Baja outright-ban clause is narrower (only epígrafe
    10.4 "restaurantes con amenización de música en directo", not the
    whole "con música" hostelería category like the other three zones).
  - Centro's distance thresholds are roughly double the other zones'
    (200/150/100m in Moderada vs Trafalgar/Gaztambide's 100/75/50m), and
    uniquely extends the distance requirement to "sin_superacion"
    competitors too (50m in Moderada, 75m in Baja) -- no other zone's
    Normativa mentions that classification as a competitor trigger at all.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationRule:
    prohibited_outright: bool = False
    prohibited_with_music: bool = False
    # required minimum distance (metres) to an EXISTING competing venue,
    # keyed by THAT venue's street classification -- only meaningful when
    # not prohibited_outright. A missing key means no restriction from
    # that competitor classification in this zone.
    min_distance_m: dict = None


@dataclass(frozen=True)
class ZpaeZone:
    name: str
    clasificacion_name: str
    district: str
    in_force_since: str
    normativa_pdf: str  # source filename in docs/normativa_pdfs/
    # keyed by Clasifica classification on the CANDIDATE's own street; a
    # classification absent from this dict means the zone has no streets
    # of that classification at all (confirmed against the shapefile).
    rules: dict = None
    notes: str = ""


ZONES = [
    ZpaeZone(
        "ZPAE Centro", "ZPAE Distrito Centro", "Centro", "2018",
        normativa_pdf="NormativaZPAECentro2018Def_art21_anul.pdf",
        rules={
            "alta": ClassificationRule(prohibited_outright=True),
            "moderada": ClassificationRule(
                prohibited_with_music=True,
                min_distance_m={
                    "alta": 200, "moderada": 150, "baja": 100,
                    "sin_superacion": 50,
                },
            ),
            "baja": ClassificationRule(
                min_distance_m={
                    "alta": 300, "moderada": 150, "baja": 100,
                    "sin_superacion": 75,
                },
            ),
            "sin_superacion": ClassificationRule(),  # unregulated
        },
        notes=(
            "Article 21 ('Distancia de protección', a zone-boundary-level "
            "150/125/100m rule layered on top of Art. 9/12/15) is struck "
            "through in the source PDF with a footnote: annulled by "
            "Tribunal Superior de Justicia de Madrid, sentencia 127/2022, "
            "Procedimiento Ordinario 557/2019 -- NOT in effect. This is "
            "the court challenge the README referenced; resolved as void, "
            "not as an open question."
        ),
    ),
    ZpaeZone(
        "ZPAE Gaztambide", "ZPAE Barrio Gaztambide", "Chamberí",
        "2016 (extension of Aurrerá ZPAE); modificación 2022-06-17",
        normativa_pdf="NormZPAEGaztambideAprobFinal.pdf",
        rules={
            "alta": ClassificationRule(prohibited_outright=True),
            "moderada": ClassificationRule(
                prohibited_with_music=True,
                min_distance_m={"alta": 100, "moderada": 75, "baja": 50},
            ),
            "baja": ClassificationRule(
                min_distance_m={"alta": 150, "moderada": 75, "baja": 50},
            ),
            "sin_superacion": ClassificationRule(),  # unregulated
        },
        notes=(
            "2022 modificación (BOAM 9.161, acuerdo 1849, "
            "docs/normativa_pdfs/BOAM2022_ZPAEGaztambide9161-1849.pdf) "
            "only replaced the street delimitation tables (Art. 8/11/14) "
            "and alcohol-sale hours (Art. 19.2) -- did NOT touch the "
            "régimen/distance articles (9/12/15), so these numbers are "
            "still current. The live zpae_clasificacion.shp download "
            "should already reflect the 2022 delimitation since it's a "
            "fresh pull, not the original 2016 boundaries."
        ),
    ),
    ZpaeZone(
        "ZPAE Azca Av. de Brasil", "ZPAE AZCA-Av de Brasil", "Tetuán",
        "2015-01-27; modificación 2022-06-17",
        normativa_pdf="NormativaZPAEn14.pdf",
        rules={
            # No "alta" entry: AZCA has no Alta chapter at all, confirmed
            # by zpae_clasificacion.shp only ever showing Baja/Moderada.
            "moderada": ClassificationRule(
                prohibited_with_music=True,
                min_distance_m={"alta": 100, "moderada": 75, "baja": 50},
            ),
            "baja": ClassificationRule(
                min_distance_m={"alta": 100, "moderada": 75, "baja": 30},
            ),
            # No "sin_superacion" entry: no such chapter either.
        },
        notes=(
            "NormativaZPAEn14.pdf's Art. 9.2 (100/75/50) and Art. 12.1 "
            "(...30m for baja) numbers already match the 2022 "
            "modificación's replacement text (BOAM 9.161, acuerdo 1848, "
            "docs/normativa_pdfs/BOAM2022_ZPAEAzca9161-1848.pdf) -- this "
            "PDF is read as the current, already-consolidated version, "
            "not the pre-2022 original. UNRESOLVED DISCREPANCY: the "
            "modificación's text says 'se suprime el apartado 2' of "
            "Art. 12 (that apartado should be empty), but the PDF still "
            "shows Art. 12.2 with content (non-residential-building "
            "restriction for clase III/IV). Flagging rather than "
            "silently resolving -- verify against the BOCM-published "
            "consolidated text if this zone's edge cases matter later. "
            "AZCA's own outright-ban clause is also narrower than the "
            "other three zones': only epígrafe 10.4 (restaurants with "
            "live music) is banned outright in Moderada, not all "
            "'con música' hostelería, and Baja's ban list doesn't "
            "mention categoría 10 at all -- plain hostelería is never "
            "banned outright in AZCA, only distance-gated."
        ),
    ),
    ZpaeZone(
        "ZPAE Trafalgar Rios Rosas", "ZPAE Trafalgar-Ríos Rosas",
        "Chamberí", "2023-01-09",
        normativa_pdf="NormaPlanZonalZPATrafalgarRR_22.pdf",
        rules={
            "alta": ClassificationRule(prohibited_outright=True),
            "moderada": ClassificationRule(
                prohibited_with_music=True,
                min_distance_m={"alta": 100, "moderada": 75, "baja": 50},
            ),
            "baja": ClassificationRule(
                min_distance_m={"alta": 150, "moderada": 75, "baja": 50},
            ),
            "sin_superacion": ClassificationRule(),  # unregulated
        },
    ),
]

# The REST MapServer below returns geometry=null on every query variant
# tried (server-side bug, not fixable client-side) -- use the Geoportal zip
# download instead. See scripts/01_fetch_zpae.py and docs/data_sources.md.
ZPAE_MAPSERVER = "https://sigma.madrid.es/hosted/rest/services/MEDIO_AMBIENTE/ZPAE/MapServer"
ZPAE_ZIP_URL = (
    "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/"
    "MEDIO_AMBIENTE/INFORMACION_ACUSTICA/ZPAE/ZPAE.zip"
)
