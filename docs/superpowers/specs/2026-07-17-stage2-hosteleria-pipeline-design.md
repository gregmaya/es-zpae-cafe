# Stage 2: Hostelería competitor data + candidate address context

## Purpose

Stage 1 established the distance-threshold rule per zone (`src/zones.py`) and
clipped the street network + address points to the four ZPAE zones. Stage 2
builds two things off the same underlying data source:

1. The point layer of *existing* activities a candidate address must keep
   distance from (the "competitor" dataset).
2. Commercial-use context for every candidate address point, so the tool can
   answer "could a hostelería open *here*" for any address — not just
   currently-vacant ones.

### Why both belong in Stage 2

The Normativa text (confirmed in Stage 1, verbatim across all four zones)
gates new hostelería based on proximity to a broader activity set than just
other cafés/bars — clase III (espectáculos: salas de fiestas,
café-espectáculo...), clase IV (discotecas), clase V categoría 9
(bares de copas/ocio), and clase V categoría 10 (hostelería y restauración,
the plain cafés/bars this project models as the *candidate* activity). All
four classes must be in the competitor dataset, or a candidate near a
nightclub or live-music venue would incorrectly show as clear.

Separately: the ZPAE distance rule applies regardless of an address's
*current* use — Art. 3 in every Normativa treats urbanistic-use compatibility
as a distinct, prior check, not part of the ZPAE rule itself. A shoe shop
closing and reopening as a café is a real scenario this tool should answer,
not just currently-vacant premises. That means the candidate universe can't
just be "every address point" (`rt_portalpk_p` includes purely residential
doors too, which aren't realistic hostelería candidates) — it needs
commercial-local context to be useful. Both the competitor dataset and this
context come from the same source dataset, so building them together avoids
fetching `200085-5-censo-locales` twice.

## Non-goals for this stage

- Terrazas (resource `200085-6-censo-locales`): no activity code of its own,
  and the Normativa measures from the indoor "puerta del local," not the
  terrace footprint. Deferred to a later display-enrichment stage, not
  required for the core distance calculation.
- Network-distance computation itself (Cityseer graph building, per-street
  threshold evaluation): that's Stage 3/4.
- Urbanistic-use compatibility (Art. 3's separate check, e.g. zoning that
  might block a residential-to-commercial conversion regardless of ZPAE):
  out of scope for this project entirely, not just this stage — the tool
  answers the ZPAE distance question, not general licensing viability.

## Data source

CKAN datastore API on datos.madrid.es (`https://datos.madrid.es/api/3/action/`),
resource `200085-5-censo-locales` — the "actividad" slice of the citywide
"censo de locales y actividades" dataset (225,268 total records). Confirmed
via direct API queries (2026-07-17):

- Carries everything needed in one resource: `coordenada_x_local` /
  `coordenada_y_local`, `id_situacion_local` / `desc_situacion_local`
  (status), `rotulo` (name), and the CNAE-based `id_seccion`/`desc_seccion`,
  `id_epigrafe`/`desc_epigrafe` activity classification. No null
  coordinates citywide (checked).
- Three sibling resources exist (`-1` identificación, `-3` licencia, `-6`
  terrazas) but are redundant subsets for our purposes or not required (see
  Non-goals) — not pulled in this stage.
- `id_situacion_local` breakdown, citywide: Abierto 159,573 · Cerrado 40,272
  · Baja 12,567 · Uso vivienda 8,480 · Baja Reunificación 4,376. "Uso
  vivienda" (converted to residential) is excluded everywhere below — it's
  no longer a commercial premises. The others are all kept: "Cerrado" is
  exactly the vacant-but-commercial case motivating this stage's candidate
  work; "Baja"/"Baja Reunificación" (deregistered/merged) are kept as
  informational context but not treated as separately available units.
- Pagination: CKAN datastore endpoints cap results per request (same
  failure mode as Stage 1's ArcGIS `exceededTransferLimit` bug) — fetch
  script MUST assert the fetched row count matches the API's reported
  `total`, not just stop when a page looks short.
- **One citywide pull, not two.** Rather than fetching the `id_seccion IN
  ('I','R')` subset separately from a full pull, fetch everything
  (excluding only "Uso vivienda") once and derive both the competitor
  subset and the candidate-context tagging from it client-side.

## Activity classification mapping

New file `src/activities.py`, structured like `src/zones.py`'s
`ClassificationRule` pattern. Maps `id_epigrafe` → Decreto 184/1998
class/categoría, built by cross-referencing the confirmed epígrafe list
against each Normativa PDF's Art. 4 activity catalog (all four zones use
near-identical Art. 4 text). This mapping only applies to seccion I/R rows
(the only sections with ZPAE-relevant activity types) — the unmapped-code
warning below is scoped to those two sections, not the full citywide set,
since general retail/industry epígrafes have no Decreto 184/1998 equivalent
and aren't meant to be mapped.

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
unmapped rather than guessed. Any seccion I/R epígrafe encountered in the
live data that isn't in this table (mapped or explicitly excluded) must be
surfaced by the fetch script, not silently dropped.

## Pipeline

Same fetch → reconcile split as Stage 1, for the same reason: keep the raw
ground-truth dump inspectable before a reviewed mapping gets applied.

### `scripts/03_fetch_hosteleria.py`

1. Query `datastore_search_sql` for `id_situacion_local != '5'` (i.e.
   everything except "Uso vivienda"), paginating until the fetched count
   matches the reported `total`.
2. Print every distinct `(id_epigrafe, desc_epigrafe)` encountered **within
   seccion I/R** that is NOT in `src/activities.py`'s mapping table (mapped
   or excluded) — loud warning, not a silent drop. Sections outside I/R are
   not checked against this mapping.
3. Save the raw citywide result as `data/raw/hosteleria/censo_locales_full.geojson`
   (point geometry built from `coordenada_x_local`/`coordenada_y_local`, CRS
   EPSG:25830 — spot-check bounds against known Madrid extent as a sanity
   check, same pattern as Stage 1's clip debugging).

### `scripts/04_reconcile_hosteleria.py`

Loads the one raw pull and produces two outputs:

#### A. Competitor point layer

1. Filter to seccion I/R + `desc_situacion_local == 'Abierto'` (only
   currently-open activities are real competitors).
2. Apply `src/activities.py`: tag each row with its Decreto class, drop rows
   whose epígrafe is in the "excluded" list, drop (and report count of) any
   row whose epígrafe is neither mapped nor excluded.
3. Clip to the four-zone study area buffer, reusing the dissolve+buffer
   logic from `scripts/02_clip_network_to_zpae.py` (same 300m buffer, same
   `zpae_ambitos.geojson` input).
4. Save `data/processed/hosteleria_competitors_zpae_clip.gpkg`, tagged with
   Decreto class per point.
5. Report per-zone / per-class counts after clipping as a sanity check
   (matching Stage 1's "4380 street segments" reporting style).

#### B. Candidate address context

1. Start from `data/processed/rt_portalpk_p_zpae_clip.gpkg` (Stage 1's
   clipped address points, 13,876 points) as the fixed candidate universe —
   one point per address door, not per commercial unit, matching the
   project's "building-by-building map" goal.
2. Spatial-join each address point to the nearest local(s) in the full
   citywide pull (from step A's pre-clip data, not re-clipped — a local
   just outside the study buffer could still be the nearest match to an
   address right at the buffer edge) within a small distance tolerance.
   Tolerance value TBD empirically: start with 15m (a local's street door
   and its building's official address point should be within a few
   metres of each other in dense urban blocks); inspect the distribution of
   match distances on real data before trusting this cutoff, and widen or
   flag outliers as needed rather than assuming 15m is right.
3. For each address point, summarize: `has_commercial_local` (bool — any
   match found at all), `current_activity_summary` (list of
   `(id_seccion, desc_epigrafe, situacion)` for all matched locals — an
   address can have multiple units), and `is_existing_hostelería_class`
   (bool — does it already match a seccion I/R Decreto-mapped epígrafe,
   meaning it's simultaneously a candidate for modification AND already
   counted as a competitor for everyone else's distance check).
4. Save `data/processed/candidate_addresses_zpae_clip.gpkg` — the address
   points enriched with this context, superseding the plain
   `rt_portalpk_p_zpae_clip.gpkg` as the artifact later stages should build
   on for "which addresses can we evaluate."

## Error handling / data quality checks

- Pagination completeness assert (fetched count == API `total`).
- Unmapped-epígrafe warning (fetch script, seccion I/R only) and hard
  exclusion-vs-unmapped distinction (reconcile script) — never silently
  merge the two.
- CRS sanity check on raw coordinates (bounds should fall within Madrid's
  known EPSG:25830 extent — same style of check used when debugging the
  IGR-RT CRS in Stage 1).
- Zero-features-after-clip would indicate a bug (as it did in Stage 1's
  script 02 before the file-path fix) — report counts, don't proceed
  silently if a zone comes back empty.
- Report the distribution of nearest-local match distances (min/median/p95/
  max) for the candidate-context join, and the count of addresses with NO
  match within tolerance — both are needed to sanity-check the 15m
  assumption before trusting it, not just to log it.

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
- Address-to-local join tolerance (15m starting assumption) needs empirical
  validation against the real match-distance distribution before Stage 5
  relies on it — see error handling above.
- Addresses with no nearby commercial local at all (pure residential):
  still included in the output with `has_commercial_local = False` rather
  than dropped, since Art. 3's separate urbanistic-compatibility check
  (out of scope here) is what would actually gate those, not the ZPAE rule
  itself — but downstream stages/UI should probably surface this flag
  rather than silently evaluate them the same as commercial addresses.
