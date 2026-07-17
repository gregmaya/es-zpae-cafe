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
