# Stage 2: Hostelería competitor data pipeline

## Purpose

Stage 1 established the distance-threshold rule per zone (`src/zones.py`) and
clipped the street network + address points to the four ZPAE zones. Stage 2
builds the other half of the distance calculation: the point layer of
*existing* activities a candidate address must keep distance from.

The Normativa text (confirmed in Stage 1, verbatim across all four zones)
gates new hostelería based on proximity to a broader activity set than just
other cafés/bars — clase III (espectáculos: salas de fiestas,
café-espectáculo...), clase IV (discotecas), clase V categoría 9
(bares de copas/ocio), and clase V categoría 10 (hostelería y restauración,
the plain cafés/bars this project models as the *candidate* activity). All
four classes must be in the competitor dataset, or a candidate near a
nightclub or live-music venue would incorrectly show as clear.

## Non-goals for this stage

- Candidate address points: already have `rt_portalpk_p` (IGR-RT, clipped in
  Stage 1) — not re-sourced from Catastro/Callejero.
- Terrazas (resource `200085-6-censo-locales`): no activity code of its own,
  and the Normativa measures from the indoor "puerta del local," not the
  terrace footprint. Deferred to a later display-enrichment stage, not
  required for the core distance calculation.
- Network-distance computation itself (Cityseer graph building, per-street
  threshold evaluation): that's Stage 3/4.

## Data source

CKAN datastore API on datos.madrid.es (`https://datos.madrid.es/api/3/action/`),
resource `200085-5-censo-locales` — the "actividad" slice of the citywide
"censo de locales y actividades" dataset (225,268 total records). Confirmed
via direct API queries (2026-07-17):

- Carries everything needed in one resource: `coordenada_x_local` /
  `coordenada_y_local`, `id_situacion_local` / `desc_situacion_local`
  (open/closed status), `rotulo` (name), and the CNAE-based
  `id_seccion`/`desc_seccion`, `id_epigrafe`/`desc_epigrafe` activity
  classification.
- Three sibling resources exist (`-1` identificación, `-3` licencia, `-6`
  terrazas) but are redundant subsets for our purposes or not required (see
  Non-goals) — not pulled in this stage.
- Query via `datastore_search_sql`, filtered server-side to
  `id_seccion IN ('I','R') AND desc_situacion_local = 'Abierto'` — cuts
  225k → 31,536 rows citywide before any geographic clipping. Section `I`
  is Hostelería; section `R` is Actividades artísticas, recreativas y de
  entretenimiento (covers discotecas, salas de fiesta, etc.).
- Pagination: CKAN datastore endpoints cap results per request (same
  failure mode as Stage 1's ArcGIS `exceededTransferLimit` bug) — fetch
  script MUST assert the fetched row count matches the API's reported
  `total`, not just stop when a page looks short.

## Activity classification mapping

New file `src/activities.py`, structured like `src/zones.py`'s
`ClassificationRule` pattern. Maps `id_epigrafe` → Decreto 184/1998
class/categoría, built by cross-referencing the confirmed epígrafe list
against each Normativa PDF's Art. 4 activity catalog (all four zones use
near-identical Art. 4 text).

| Decreto class | Epígrafes | Confidence |
|---|---|---|
| Clase III Cat.1 (esparcimiento y diversión) | 563007 (café-espectáculo), 932004 (salas de fiesta con restauración), 932005 (salas de fiesta sin restauración) | confident |
| Clase III Cat.2 (culturales y artísticos) | *(none — no exact "salas de conciertos" epígrafe exists in this dataset)* | **unmapped, documented gap** |
| Clase IV Cat.4 (de baile) | 932006 (discotecas y salas de baile) | confident |
| Clase V Cat.9 (ocio y diversión) | 563002 (bar especial sin actuaciones), 563003 (bar especial con actuaciones) | confident |
| Clase V Cat.10 (hostelería y restauración) | 561001–561007 (restaurante, comida rápida, autoservicio, bar-restaurante, bar con cocina, cafetería, chocolatería/salón de té), 563001 (bodega con consumo), 563004 (taberna), 563005 (bar sin cocina), 562101 (salón de banquetes) | confident |
| excluded (deliberate) | 561008 (vendedor ambulante / restauración móvil — no fixed premises), 562901–562905 (captive institutional catering: comedores de empresa/colegio/hospital, not open to the public), 563006 (ciber-café) | excluded, not gated by ZPAE hostelería rules |
| edge case | hotel bars/restaurants with direct street access (subset of 551001/551002) | **unmapped — census doesn't tag street-access separately from other hotel restaurants** |

Two documented gaps (Clase III Cat.2, hotel street-access bars) are left
unmapped rather than guessed. Any epígrafe encountered in the live data that
isn't in this table (mapped or explicitly excluded) must be surfaced by the
fetch script, not silently dropped.

## Pipeline

Same fetch → reconcile split as Stage 1, for the same reason: keep the raw
ground-truth dump inspectable before a reviewed mapping gets applied.

### `scripts/03_fetch_hosteleria.py`

1. Query `datastore_search_sql` for `id_seccion IN ('I','R') AND
   desc_situacion_local = 'Abierto'`, paginating until the fetched count
   matches the reported `total`.
2. Print every distinct `(id_epigrafe, desc_epigrafe)` encountered that is
   NOT in `src/activities.py`'s mapping table (mapped or excluded) — loud
   warning, not a silent drop.
3. Save the raw citywide result as
   `data/raw/hosteleria/censo_locales_seccion_i_r.geojson` (point geometry
   built from `coordenada_x_local`/`coordenada_y_local`, CRS EPSG:25830 —
   spot-check bounds against known Madrid extent as a sanity check, same
   pattern as Stage 1's clip debugging).

### `scripts/04_reconcile_hosteleria.py`

1. Load the raw pull.
2. Apply `src/activities.py`: tag each row with its Decreto class, drop
   rows whose epígrafe is in the "excluded" list, drop (and report count of)
   any row whose epígrafe is neither mapped nor excluded.
3. Clip to the four-zone study area buffer, reusing the dissolve+buffer
   logic from `scripts/02_clip_network_to_zpae.py` (same 300m buffer,
   same `zpae_ambitos.geojson` input).
4. Save `data/processed/hosteleria_competitors_zpae_clip.gpkg`, tagged
   with Decreto class per point.
5. Report per-zone / per-class counts after clipping as a sanity check
   (matching Stage 1's "4380 street segments" reporting style).

## Error handling / data quality checks

- Pagination completeness assert (fetched count == API `total`).
- Unmapped-epígrafe warning (fetch script) and hard exclusion-vs-unmapped
  distinction (reconcile script) — never silently merge the two.
- CRS sanity check on raw coordinates (bounds should fall within Madrid's
  known EPSG:25830 extent — same style of check used when debugging the
  IGR-RT CRS in Stage 1).
- Zero-features-after-clip would indicate a bug (as it did in Stage 1's
  script 02 before the file-path fix) — report counts, don't proceed
  silently if a zone comes back empty.

## Open questions / deferred decisions

- Clase III Cat.2 ("salas de conciertos y asimilables") has no matching
  epígrafe in this dataset — may need a different data source later, or an
  accepted gap if concert halls are rare/irrelevant in these four zones.
- Hotel bars/restaurants with direct street access: census doesn't
  distinguish these from other hotel amenities; would need manual
  cross-reference (e.g. against Catastro) if this edge case turns out to
  matter for the four zones in scope.
- Terrazas (resource `-6`) deferred — revisit if/when the web app needs to
  display terrace footprints, or if door-vs-terrace measurement point
  becomes contested.
