# es-zpae-cafe

Geospatial viability tool for new hostelería (café/bar) licences inside Madrid's
Zonas de Protección Acústica Especial (ZPAE). Given a candidate address, tells you
whether it clears the minimum network-distance threshold to the nearest existing
hostelería local, per the applicable zone's classification (alta / moderada / baja /
sin superación). Outputs a static, precomputed building-by-building map plus
address search.

Standalone repo — not part of the Healthy Transport modular stack, though it
borrows the same conventions (Python, GeoPandas, ETRS89/EPSG:25830 as native CRS,
reprojecting to EPSG:4326 only for the web layer).

## Status

**Stage 1 (ground truth the rule) is complete.** All four zones' distance
thresholds are parsed and encoded in [`src/zones.py`](src/zones.py), sourced
directly from each zone's "Normativa del Plan Zonal Específico" PDF — see
[`docs/data_sources.md`](docs/data_sources.md) for the full findings,
including a real service bug in the ArcGIS REST endpoint and a
court-annulled article in Centro's plan.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`scripts/01_fetch_zpae.py` downloads the ZPAE zone/classification shapefiles.
`scripts/02_clip_network_to_zpae.py` needs a separately-downloaded IGR-RT
geopackage (Comunidad de Madrid extent, `rt_tramo_vial` + `rt_portalpk_p`
layers) — see `docs/data_sources.md` for where to get it. Neither the
downloaded data nor the normativa PDFs are committed to this repo (see
`.gitignore`); the PDFs were sourced manually since the official `Enlace`
links block scripted fetches (403).

## License

Code is MIT-licensed (see [`LICENSE`](LICENSE)). This does **not** cover the
underlying datasets (IGN/CNIG's IGR-RT network, Ayuntamiento de Madrid's ZPAE
and censo de locales data), which remain under their original publishers'
terms and are not redistributed in this repo.

## Scope

Four ZPAE zones exist in Madrid as of this writing:

| Zone | District | In force since |
|---|---|---|
| Centro | Centro | (oldest; revised April 2019) |
| Gaztambide (ex-Aurrerá) | Chamberí | Nov 2016 (extension) |
| AZCA-Av. Brasil | Tetuán | Jan 2015 |
| Trafalgar-Ríos Rosas | Chamberí | 9 Jan 2023 |

All four are in scope for the pilot.

**Known gap to close in Stage 1**: the ArcGIS MapServer service description text
only mentions three zones (Centro, Gaztambide, AZCA) — that's stale copy, not
necessarily the live layer content. First task is querying the actual `Normativa`
field on layer 4 to confirm Trafalgar-Ríos Rosas is present and to extract the
real per-zone, per-classification distance thresholds (these are NOT uniform
across zones — see docs/data_sources.md).

## Stages

1. **Ground truth the rule** — query ZPAE layer 4, extract `ZPAE` / `ZonaSupera` /
   `Normativa` per polygon for all four zones; parse the actual metre thresholds
   out of `Normativa` text (don't hardcode assumed numbers).
2. **Data pipeline** — ingest ZPAE polygons, censo de locales + terrazas (filtered
   to hostelería epígrafes), Catastro/Callejero address points. Reconcile CRS
   (native EPSG:25830).
3. **Network graph** — build a Cityseer-compatible graph from IGN/CNIG's
   IGR-RT official street network (`rt_tramo_l` + node/relation tables,
   filtered to urban, Ayuntamiento-owned, pedestrian-accessible segments —
   see docs/data_sources.md) for the four zones combined; snap existing
   hostelería locations and candidate address points onto it.
4. **Distance engine** — per candidate address: network distance (not euclidean)
   to nearest hostelería local, evaluated against the classification-specific
   threshold for that street, pass/fail + margin in metres.
5. **Precompute** — run the engine over every address point in the four zones,
   bake to a static GeoJSON/vector-tile scoring layer.
6. **Web app** — Leaflet/MapLibre static site: building-by-building shading +
   address search, no backend. Deployable as static files (GitHub Pages or
   similar).

## Non-goals for v1
- No live Cityseer queries in the browser — everything precomputed offline.
- No coverage outside the four declared ZPAE polygons (outside them, no
  distance restriction applies at all under this rule).
