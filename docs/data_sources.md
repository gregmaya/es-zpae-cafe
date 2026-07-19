# Data sources

## 1. ZPAE zones (the regulatory layer)

**Update after Stage 1 ground-truthing (2026-07-17): the ArcGIS REST query
endpoint below is unusable for geometry, and the actual data model differs
from what was originally assumed here. See "What we actually found" below
before touching this section's original plan.**

Service: `https://sigma.madrid.es/hosted/rest/services/MEDIO_AMBIENTE/ZPAE/MapServer`

Layers (per live service metadata, confirmed via `<MapServer>?f=json`):
- `0` Ámbitos ZPAE E<100.000 (4 features)
- `1` Clasificación ZPAE E<100.000 (3241 features)
- `2` Clasificación ZPAE >100.000 (3241 features — same OBJECTIDs/attributes
  as layer 1, just a coarser-scale rendering duplicate)
- `3` Ámbitos ZPAE E>100.000 (4 features)
- `4` Detalle clasificación (2590 features) — **do not use**, see below.

**Geometry bug**: every query variant tried against this REST endpoint
(`outSR` on/off, spatial-envelope filter, `f=geojson`/`json`/`pbf`, browser
User-Agent) returns `geometry: null` on every single feature, for every
layer, including layer 0's 4-feature ámbitos. `returnExtentOnly=true`
confirms real polygon geometry exists server-side (extent matches central
Madrid in EPSG:25830), so the service is genuinely broken/misconfigured for
geometry serving via `/query` — not a client-side mistake. No WFS is
exposed (`supportedExtensions` on the MapServer root is WMS-only); WMS
`GetFeatureInfo` could work per-pixel but isn't a practical bulk-vector
path. **Do not spend further time on this REST endpoint.**

**Working alternative**: direct shapefile download from the Ayuntamiento's
own Geoportal, which has real geometry:
```
https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/MEDIO_AMBIENTE/INFORMACION_ACUSTICA/ZPAE/ZPAE.zip
```
This is what `scripts/01_fetch_zpae.py` now uses. CRS: EPSG:25830.

### What we actually found (data model correction)

The zip contains two shapefiles with a materially different structure than
originally assumed:

- **`ZPAE.shp`** — 4 polygons, one per zone (the "ámbito"/boundary).
  Fields: `ZPAE` (zone name), `Id`. No classification, no threshold.
- **`ZPAE_clasificacion.shp`** — 3241 **LINE segments**, not polygons. The
  alta/moderada/baja/sin-superación classification (field `Clasifica`) is a
  **per-street-segment** attribute, not a per-area one. This actually
  matches the project's own premise (threshold varies per street) and
  should make joining to the IGR-RT network more natural at Stage 3/4.
  Fields: `ZPAE`, `Clasifica`, `Enlace` (URL), `Observa` (boilerplate
  disclaimer, not useful data).

**Zone-name spelling differs between the two shapefiles** — don't join on
the `ZPAE` text field directly:
- `ZPAE.shp`: `ZPAE Azca Av. de Brasil` / `ZPAE Centro` / `ZPAE Gaztambide`
  / `ZPAE Trafalgar Rios Rosas`
- `ZPAE_clasificacion.shp`: `ZPAE AZCA-Av de Brasil` / `ZPAE Distrito
  Centro` / `ZPAE Barrio Gaztambide` / `ZPAE Trafalgar-Ríos Rosas`

All 4 zones (including Trafalgar-Ríos Rosas) are confirmed present in both
files — the "known gap" flagged in the README is resolved. The old
"3-zone stale service description" concern was about REST metadata text,
not the actual feature data, and doesn't apply to this download.

**There is no numeric metre threshold anywhere in this dataset.** The field
originally assumed to hold free-text thresholds (`Normativa` on REST layer
4) doesn't exist in this data model at all — the closest equivalent,
`Enlace` on `ZPAE_clasificacion.shp`, is one URL per zone (not per
classification) pointing at a landing page, e.g.
`https://madrid.es/go/ZPAE_Centro`. **That page 403s on every scripted
fetch attempt** (confirmed with `curl` using a full browser User-Agent —
this is WAF blocking, not a bug to route around programmatically).

### Distance thresholds — confirmed for Trafalgar-Ríos Rosas, 3 zones still open

**Solved retrieval path**: madrid.es publishes ~5 PDFs per zone (acuerdo de
aprobación, análisis de viabilidad, estudio, plano de delimitación,
normativa). Only **"Normativa del Plan Zonal Específico de la Zona de
Protección Acústica Especial [zone]"** carries the operative rule — that's
the only one worth fetching per zone. Since the `Enlace` shortlinks 403 on
scripted access, a human needs to find/download that specific PDF (e.g. via
the zone's publication page on madrid.es) and share it; the other 4 PDFs
per zone aren't needed.

Trafalgar-Ríos Rosas's Normativa PDF (`docs/normativa_pdfs/
NormaPlanZonalZPATrafalgarRR_22.pdf`, in force 2023-01-09) has been read in
full. Key findings, encoded in `src/zones.py`:

- **The rule is not a flat "classification → metres" table.** It depends on
  BOTH the classification of the candidate's own street (which regime
  applies) AND the classification of the nearest existing competing
  venue's street (which distance applies) — and it's asymmetric (e.g. a
  Baja-zone candidate needs 150m from an Alta-zone competitor, but a
  Moderada-zone candidate only needs 100m from the same competitor).
- **Alta**: new hostelería/ocio licences banned outright, no distance
  escape (Art. 10.1).
- **Moderada**: banned outright for the "con música" variant; plain
  hostelería (no music) needs ≥100m from an existing venue on an Alta
  segment, ≥75m from Moderada, ≥50m from Baja (Art. 13.1–2).
- **Baja**: needs ≥150m from Alta, ≥75m from Moderada, ≥50m from Baja
  (Art. 16.1).
- **Sin superación**: not mentioned in any restrictive chapter — no ZPAE
  distance rule applies there at all.
- Classification is determined by **the street segment where the public
  access is** (Art. 6) — confirms `ZPAE_clasificacion.shp` being a
  per-street LINE layer (not polygon) is the correct data model, and that
  joining candidate/competitor addresses to their nearest classified
  street segment is the right approach for Stage 3/4.
- Measurement method confirmed explicitly (Art. 13.2 / 16.1): minimum
  distance measured **in a straight line along the axis of streets or
  public spaces, door to door** — i.e. network distance along the street
  graph, not euclidean. Confirms the Cityseer approach.

**Resolved — all four zones now parsed and encoded in `src/zones.py`.**
Rule shape does NOT generalize across zones, confirming the caution above:

- **Centro** (`NormativaZPAECentro2018Def_art21_anul.pdf`): Alta bans ALL
  hostelería outright (no music carve-out). Moderada/Baja thresholds are
  roughly double the other zones' (200/150/100m and 300/150/100m), and
  uniquely extend the distance rule to "sin superación"-classified
  competitors too (50m/75m) — no other zone's Normativa mentions that
  classification as a competitor trigger. **Article 21** (a separate
  zone-boundary-level 150/125/100m rule) is struck through in the PDF
  itself with a footnote citing its annulment by the Tribunal Superior de
  Justicia de Madrid (sentencia 127/2022, Procedimiento Ordinario
  557/2019) — this is the court challenge the README referenced; it is
  confirmed void, not an open question.
- **Gaztambide** (`NormZPAEGaztambideAprobFinal.pdf`, 2016): same rule
  *shape* as Trafalgar-Ríos Rosas (Alta = outright ban, Moderada =
  100/75/50 with music-only ban, Baja = 150/75/50). A 2022 modificación
  (`BOAM2022_ZPAEGaztambide9161-1849.pdf`) only changed street
  delimitation tables and alcohol hours, not the distance articles.
- **AZCA-Av. Brasil** (`NormativaZPAEn14.pdf`): has no Alta chapter and no
  "sin superación" chapter at all (confirmed against
  `zpae_clasificacion.shp`, which only ever shows Baja/Moderada for this
  zone). Its outright-ban clause is narrower than the other three zones'
  (only epígrafe 10.4 "restaurantes con música en directo", not all
  hostelería-with-music) — plain hostelería is never banned outright here,
  only distance-gated (Moderada 100/75/50, Baja 100/75/30). The PDF's
  numbers already match its 2022 modificación
  (`BOAM2022_ZPAEAzca9161-1848.pdf`), so it's read as the current
  consolidated text — except one unresolved discrepancy: the modificación
  says Art. 12.2 should be suppressed/empty, but the PDF still shows it
  with content. Flagged, not silently resolved; worth re-checking against
  the BOCM-published consolidated text if this zone's edge cases start to
  matter.

All source PDFs (normativas + the two 2022 modificaciones) are archived in
`docs/normativa_pdfs/`.

## 2. Hostelería locations (competitors)

- Censo de locales y actividades: `https://datos.madrid.es/dataset/` search
  "censo de locales y sus actividades" — has `id_local`, epígrafe of activity.
- Terrazas dataset (this project's uploaded PDF documents its structure):
  `200085-0-censo-locales` on datos.madrid.es. Key fields: `id_local`,
  `id_situacion_local`/`desc_situacion_local`, `coordenada_x_local`/
  `coordenada_y_local` (UTM, ED50 pre-15/09/2017, ETRS89 after), `rotulo`.
  Join to censo de locales on `id_local` to get the epígrafe and confirm
  hostelería/cafetería activity — the terrazas file itself doesn't carry
  activity codes by design (per the PDF's own description).

## 3. Address points

- Catastro (Sede Electrónica del Catastro, INSPIRE Direcciones service) —
  authoritative parcel/address geometry.
- Madrid Callejero (`CALLEJERO/CALLEJERO_VIALES` and `CALLEJERO_SUBVIALES`
  MapServers on sigma.madrid.es) — ~200,000 portal/building points with
  postal code, SER zone, cadastral parcel linkage. Good for admin joins,
  not built for network routing.

## 4. Street network for Cityseer

**Superseded OSM plan — use IGN's IGR-RT instead.**

Madrid's own Callejero WFS publishes street **reach polygons** (recintos de
viales) — designed for addressing, not a routable centerline graph. Better
source found: IGN/CNIG's **IGR-RT** (Información Geográfica de Referencia de
Redes de Transporte), downloadable from
`https://centrodedescargas.cnig.es`. Physical model spec:
`https://centrodedescargas.cnig.es/CentroDescargas/documentos/ModeloF%C3%ADsico_IGR-RT_V1_9_publicado.pdf`.

Relevant tables (road network module):
- `rt_tramo_l` — LineString segments, the actual network edges. Key fields
  for filtering: `tipo_vial` (2001-2999 = urban street types per INE code —
  use this to isolate urban viario from interurban roads), `titular` (5 =
  Ayuntamiento, to isolate municipally-owned streets), `tipovehic`
  (`100` = peatonal only, `111` = vehicles+bikes+pedestrians — use to build
  the walkable subgraph), `clase` (2000 urbano / 2001 urbano diseminado),
  `sentido`, `firme`.
- `rt_vial_a` — the vial (named street) that groups tramos; `id_vial`,
  `nombre`, `dgc_via` (Catastro linkage — useful for joining to the
  Catastro address points from Stage 2).
- `rt_nodoctra_p` — network nodes (unions, dead-ends, infrastructure
  access points).
- `rrt_tramo_vial` — tramo-vial relation.
- `rrt_nodoctra_tramo` — node-tramo relation (this is what gives ready-made
  topology to build a networkx graph without a cleaning pass).

CRS: not stated in the excerpt fetched — confirm on download (Spanish
national geo data is typically ETRS89, either geographic EPSG:4258 or a UTM
zone; reproject to EPSG:25830 to match the ZPAE layer before any distance
work).

Action for Stage 1/3: locate the actual download product for IGR-RT
(Comunidad de Madrid extract or full Spain, filterable) on
centrodedescargas.cnig.es, confirm format (GML per the INSPIRE mapping in
section 4 of the spec, or shapefile), and confirm CRS on the real file
before building the loader. Use `dgc_via` to cross-check against the
Catastro/Callejero address data pulled in Stage 2 — this table appears
purpose-built to bridge the two.

## 5. Hostelería competitor data + candidate address context (Stage 2)

**CKAN datastore API** (`https://datos.madrid.es/api/3/action/`): the
"censo de locales y actividades" dataset exposes four sibling resources
under a single dataset ID:

- `200085-1-censo-locales` — "identificación" (base location/address, no
  activity code), 203,456 records. Not used.
- `200085-3-censo-locales` — "licencia" (licence status), 216,984 records.
  Not used.
- `200085-5-censo-locales` — "actividad" (location + CNAE-based activity
  epígrafe), 225,268 records. **This is the one used.** It already carries
  everything needed: coordinates, status, name, and activity classification,
  so the other three resources were redundant for this project's purposes.
- `200085-6-censo-locales` — "terrazas" (outdoor seating permits), 6,576
  records. Not used — no activity code of its own, and the Normativa
  measures from the indoor "puerta del local," not the terrace footprint
  (deferred to a possible later display-enrichment stage).

**Status-code breakdown** of `200085-5-censo-locales`, citywide (`id_situacion_local`):
Abierto 159,573 · Cerrado 40,272 · Baja 12,567 · Uso vivienda 8,480 · Baja
Reunificación 4,376. Total: 225,268.

Only "Uso vivienda" (residential conversion, no longer commercial) was
excluded from the fetch — all other statuses were kept, including "Cerrado"
(vacant-but-commercial premises), because the ZPAE rule applies regardless
of an address's current occupancy, not just to currently-occupied venues (see
`docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md` for
the fuller reasoning).

**Fetch result**: `id_situacion_local != '5'` (excludes only Uso vivienda)
→ 216,788 records fetched from the live API (2026-07-18). Pagination
completeness asserted against the API's reported total — matches Stage 1's
ArcGIS truncation-bug lesson: this CKAN API also caps rows per request and
required the same paginate-until-total-matches discipline.

**Activity classification** (`src/activities.py`): maps `id_epigrafe` (CNAE-based)
to the Decreto 184/1998 class/categoría scheme used in every ZPAE Normativa
(Clase III Cat.1/Cat.2, Clase IV Cat.4, Clase V Cat.9/Cat.10). Only
seccion I (Hostelería) and seccion R (Actividades artísticas, recreativas y
de entretenimiento) contain ZPAE-relevant epígrafes. The mapping table itself
lives in `src/activities.py` (single source of truth) — see that file's
`EPIGRAFE_TO_DECRETO_CLASS` dict and `EXCLUDED_EPIGRAFES` set for the
~36-entry registry; the design doc references confirm each classification.

**Two documented gaps, deliberately left unmapped/excluded rather than guessed:**

1. Clase III Cat.2 ("salas de conciertos y asimilables") — no exact matching
   epígrafe exists in this dataset. Three borderline "espectáculos"-adjacent
   codes were found and excluded rather than guessed: `900001` (actividades
   de creación, artísticas y espectáculos — too broad/ambiguous, could be
   non-venue businesses), `900002` (locales de exhibiciones eróticas — only
   1 open record citywide, negligible), `900003` (teatro y actividades
   escénicas en directo — 145 open records, a plausible fit, but excluded to
   avoid guessing at the Cat.1 vs Cat.2 classification).
2. Hotel bars/restaurants with direct street access (a subset of the 551xxx
   accommodation epígrafes) — the census doesn't tag street-access separately
   from other hotel amenities, so this edge case can't be distinguished from
   ordinary hotel accommodation with the data available.

A total of 29 epígrafes surfaced as "unmapped" on the first live run, all
subsequently reviewed and excluded: 9 accommodation codes (551001-551005,
552001, 559001-559003) and 20 recreation/culture/sport codes with no
plausible reading under the Decreto scheme (900001-900003, 910001-910002,
920001-920002, 931001-931012, 932001-932002, 932007). See
`src/activities.py`'s `EXCLUDED_EPIGRAFES` for the full list with per-code
comments.

**Final pipeline results** (from `scripts/04_reconcile_hosteleria.py`, real
run against live-fetched data):

- Competitor classification: 18,513 mapped (seccion I/R, Abierto, has a
  confident Decreto class), 13,023 excluded, 0 unmapped.
- Competitor layer after clipping to the four ZPAE zones + 300m buffer:
  18,513 → 5,341 points. Saved to `data/processed/
  hosteleria_competitors_zpae_clip.gpkg` (not committed; `data/` is gitignored).
- Candidate address context: built by spatial-joining Stage 1's 13,876
  clipped `rt_portalpk_p` address points to the nearest local(s) in the
  (unclipped, citywide) `200085-5-censo-locales` pull, with a 15m distance
  tolerance. Match-distance distribution: min=0.1m, median=4.4m, p95=11.5m,
  max=15.0m (p95 comfortably below the 15m ceiling, so the tolerance isn't
  obviously truncating real matches). 1,355 / 13,876 addresses (9.8%) have no
  commercial local within 15m (flagged `has_commercial_local=False`, not
  dropped from the output). Saved to `data/processed/
  candidate_addresses_zpae_clip.gpkg` (not committed).
- Both outputs are in EPSG:25830, consistent with the rest of the project.

## 6. Walkable network graph (Stage 3)

Built with [Cityseer](https://cityseer.benchmarkurbanism.com/) (5.6.1,
confirmed installed) from `rt_tramo_vial_zpae_clip.gpkg` (Stage 1's clipped
4,380 IGR-RT street segments). Logic in `src/network.py`, orchestration in
`scripts/05_build_network_graph.py` and `scripts/06_snap_points_to_network.py`.

**The node/relation table the original plan assumed
(`rrt_nodoctra_tramo`) does not exist in this download.** Only a standalone
`rt_nodoctra_p` nodes layer and the raw segments are present. The graph is
built directly from segment geometry instead (Cityseer's
`nx_from_generic_geopandas`, matching segments to nodes by endpoint
coordinate) — the standard approach for OSM-style networks, not a
project-specific workaround.

**Underground segments are mistagged as pedestrian-accessible.** 66 of
4,380 segments are tagged `situacion=Subterráneo`, and most carry the
vehicle-access code for "pedestrian+bike+vehicle" — but manual inspection
confirmed these are real Madrid car tunnels (Princesa, Bailén, San
Vicente, the A-5/A-6/M-30 ring), not places pedestrians walk. Excluded
regardless of the vehicle-access tag. Elevated segments (10, e.g. the
Segovia viaduct) are kept — real pedestrian routes.

**`rt_tramo_vial` has duplicate rows by design** — it's a join of segments
to street names, so a segment shared by two named streets (a corner, or a
bike path overlapping a named street) appears twice under the same
`id_tramo`. Deduplicated before graph-building (8 such pairs in the clip).

**Graph is undirected.** `sentido` (one-way/two-way) is a vehicle-routing
attribute; the Normativa itself measures distance "door to door along the
axis of streets," not vehicle routing — pedestrians walk both directions
on a one-way street.

**Connectivity finding, investigated and fixed.** The first build produced
27 connected components instead of 1 (a dominant component with 97.9% of
nodes, plus 26 tiny orphan components). Confirmed not a clipping-boundary
artifact (orphan points sampled 60–422m inside the study-area buffer, two
literally inside the ZPAE Centro zone). Root cause: sub-metre
coordinate-precision mismatches at shared junctions in the source
geometry. Fixed using Cityseer's `nx_consolidate_nodes(buffer_dist=2)`
(a conservative distance, well below the library's own default of 12m,
chosen to close precision gaps without merging real distinct junctions),
reducing it to 5 components (99.7% in the dominant component). The
remaining 4 orphan pairs (8 nodes) didn't respond to a larger buffer
(3m tried, no further improvement) and are accepted as a known residual —
most likely elevated/pedestrian-bridge segments whose endpoints don't
align with the surface network. Documented directly in
`scripts/05_build_network_graph.py` so Stage 4 doesn't need to re-derive
this: any candidate/competitor point snapping to one of these orphan
nodes should be flagged as unreachable via the network, not silently
given a distance computed within an isolated 2-node fragment.

**Decomposition at 10m** via Cityseer's `nx_decompose`, chosen over 5m:
worst-case node-snapping offset at 10m is ~5m, already only ~17% of the
tightest real threshold in scope (AZCA's 30m baja-to-baja), and other
error sources in the pipeline turned out to be larger anyway (see next
finding) — going finer would have doubled the graph size for accuracy
smaller than the existing error budget.

**Point-to-node snapping offset is larger than decomposition alone would
predict — investigated, not a bug.** Snapping Stage 2's two point layers
onto the decomposed graph's nearest nodes gave offset distances with
median ~8.5m (competitors) / ~5.8m (candidates) and p95 ~21m / ~17m —
above the naive "well under 10m" expectation. Investigated by
independently measuring point-to-raw-street-*line* distance (before any
decomposition or snapping): nearly identical to the reported offset
distribution (median 8.0m, p95 20.5m for competitors). This proves the
offset is dominated by genuine geographic distance between the
address/POI points and the street centerline (building setback, plaza
addresses — normal for Madrid geocoded data), with decomposition/snapping
contributing only ~0.5m on top, exactly as designed. This offset is
tracked per point (`offset_distance_m`) for Stage 4 to add back into the
final network-distance calculation, not dropped.

Final outputs (EPSG:25830, `data/processed/`, not committed):
`network_graph_zpae.pickle` (31,931 nodes / 33,514 edges, decomposed),
`hosteleria_competitors_zpae_snapped.gpkg` (5,341 points),
`candidate_addresses_zpae_snapped.gpkg` (13,876 points).

## 7. Distance engine (Stage 4)

**Zone + street classification tagging.** Every candidate and competitor
point is tagged with (a) its ZPAE zone, via point-in-polygon against
`zpae_ambitos.geojson`, and (b) its nearest classified street's
alta/moderada/baja/sin_superacion label, via nearest-line match against
`zpae_clasificacion.geojson` within a 30m tolerance — chosen because
zone-interior points are almost always within a few metres of a classified
street in the real data, so 30m is a generous ceiling rather than a tight
fit. Logic in `src/zone_tagging.py`, orchestrated by
`scripts/07_tag_zones_and_classifications.py`.

**Real data-quality finding, not a Stage 4 bug.**
`hosteleria_competitors_zpae_snapped.gpkg` has 5,341 rows but only 5,001
unique `id_local` values — 340 duplicate rows across 308 businesses (same
business, identical coordinates and attributes, appearing more than once).
Traced to Stage 2's source census data having repeat records for the same
business. Not worth reopening Stage 2 to fix at the source, since it
doesn't affect nearest-distance correctness (duplicate rows sit at
identical positions) — it's absorbed automatically as a side effect of the
classification-tagging step's tie-breaking dedup, below.

**Tie-breaking rule.** When a point is equidistant to differently-classified
street segments, or has duplicate source rows, the more restrictive
classification wins (alta > moderada > baja > sin_superacion), grounded in
Art. 6 of the Normativa ("la zona más restrictiva" governs when there's
ambiguity).

**Real tagging results.** Candidates: 13,876 total, 9,926 fall inside a ZPAE
zone polygon, 10,080 are within 30m of a classified street, 9,838 satisfy
both (fully evaluable). Competitors: 5,341 raw rows / 5,001 unique
businesses, 3,776 inside a zone, 3,893 classified — the classified count
exceeding the in-zone count is expected and correct (see cross-zone
decision below), not a bug.

**Cross-zone competitor counting — a deliberate interpretive decision, not
a default.** The Normativa text is genuinely ambiguous about whether a
competitor sitting in a different (but nearby) ZPAE zone than the candidate
should count toward the candidate's distance check. The project's own
decision, confirmed with the project owner: yes, any nearby competitor
counts regardless of which zone it's in — only the candidate's own zone
determines which threshold rule applies. This is why competitors are gated
only on having a known classification, never on being inside any
particular zone.

**Dual distance interpretation.** The Normativa measures distance "door to
door," which arguably should include the walk from a building's door to
the street network — but this reading is genuinely disputable. Rather than
picking one interpretation silently, Stage 4 computes both: "strict"
includes the offset from each address point to the street network (both
the candidate's own and the competitor's own), "lenient" measures network
distance only. Computed via two separate
`cityseer.metrics.layers.compute_accessibilities` passes — the
competitor's own offset is folded in automatically by cityseer's
edge-assignment for the "strict" pass; a synthetic competitor layer placed
at exactly the snapped network node position (zero offset) is used for the
"lenient" pass. Both are reported, and cases where they disagree (32 out of
9,838 evaluated candidates) are flagged rather than resolved by picking a
side. Logic in `src/distance_engine.py`, orchestrated by
`scripts/08_compute_distances.py`.

**Real evaluation results.** 9,838 candidates evaluated; strict
interpretation: 1,251 pass / 8,587 fail; lenient: 1,219 pass / 8,619 fail;
32 disagree between the two — all in the direction of strict-pass /
lenient-fail, since adding the offset walk can only increase the measured
distance, never decrease it, so this is the mathematically expected
direction, not a red flag. 1,939 candidates are banned outright regardless
of distance (all are `alta`-classified in Centro, Gaztambide, or
Trafalgar-Ríos Rosas — the three zones that ban Alta-classified hostelería
outright; AZCA has no Alta chapter at all and contributes zero to this
count).

**A subtlety worth flagging for future readers.** The search cutoff for the
accessibility computation was set to 350m, comfortably above the largest
real threshold in scope (300m, used in Centro). `compute_accessibilities`'s
own internal `max_netw_assign_dist` (default 100m) caps how far a
competitor's real position can be from the network and still be included
in the "strict" pass — verified safe for this dataset (max real competitor
offset found: 61.6m, well under 100m), but this is an implicit dependency
on the current data's offset distribution, not something enforced by an
assertion in the code. Worth re-checking if this pipeline is ever re-run
against updated source data with different geocoding characteristics.

**Nearest-competitor identity (Task 5 addition).** The four lookup combinations
(strict/lenient × binding/overall) now also return the specific nearest
competitor's identity: `id_local`, `rotulo`, `desc_epigrafe`, `classification`,
`distance_m`, `x`, `y` — yielding 28 new columns total (4 groups of 7 fields
per candidate). When no competitor is found within the 350m search cutoff, or
when the relevant binding classification doesn't apply to a candidate, all
seven fields for that group are null together. Cross-reference
`docs/superpowers/specs/2026-07-19-nearest-competitor-identity-design.md` for
the full specification and rationale.

**Known limitation: strict-mode offset approximation.** The strict-mode
nearest-competitor lookup approximates each competitor's real-world offset
using its precomputed node-offset (`offset_distance_m`, the distance from
the competitor's real position to its nearest snapped network node — see
`src/network.py:snap_points_to_nearest_node`). The pass/fail engine above,
by contrast, folds each competitor's offset in via cityseer's own internal
edge-assignment (a perpendicular projection onto the nearest network edge,
not the nearest node) when computing the strict `distance_m`/margin. Both
are legitimate offset conventions, but they can diverge slightly — bounded
by roughly the ~10m node-decomposition spacing used when building the
walkable graph (`scripts/05_build_network_graph.py`'s `DECOMPOSE_MAX_M`).
In practice this means the strict-mode nearest-competitor `distance_m` is a
close approximation of, not an identical value to, the strict
distance/margin already computed by the pass/fail engine, and in rare
boundary cases near the 350m search cutoff or a rule's exact threshold, the
reported "nearest binding competitor" identity should be treated as the
practically-correct one for UI purposes, not a byte-for-byte guarantee of
exactly which competitor produced the numeric margin.

Final output (EPSG:25830, `data/processed/`, not committed):
`distance_evaluation_results.gpkg` — one row per evaluable candidate, with
strict/lenient pass-fail, margin in metres, and the binding (tightest)
classification for each interpretation, plus the nearest competitor's identity
(name, activity type, classification, distance, location) for all four lookup
combinations.
