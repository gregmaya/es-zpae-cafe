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

**In plain terms: we know the actual rules, we've mapped where every bar,
café, and nightlife venue is in the four zones, and we now have an actual
walkable street network to measure distances over.** Three stages down,
three to go before this becomes a usable map.

- **Stage 1 — done.** Read the official council documents (not blog posts
  or summaries) for all four zones to find the real minimum-distance rules.
  These turned out to be more complicated than expected — the required
  distance depends on both how "loud" the candidate's own street is
  officially classified, and how loud the street of the nearest existing
  venue is. One zone (Centro) even had a rule struck down by a court
  ruling, which we found and excluded. All of this is written down in
  [`src/zones.py`](src/zones.py), with full sourcing in
  [`docs/data_sources.md`](docs/data_sources.md).
- **Stage 2 — done.** Pulled Madrid's full public business registry
  (~217,000 active and recently-closed businesses) and worked out which
  ones count as "existing venues" a new café/bar has to keep its distance
  from — not just other cafés, but also things like nightclubs and live
  music bars, since that's what the rule actually says. Also worked out,
  for every candidate address in the four zones, what's currently there
  today (a shop, an empty unit, an existing café, nothing commercial at
  all), so the tool can later answer "could a café open *here*" for any
  address — not only ones that happen to be vacant right now. Full
  breakdown in `docs/data_sources.md`.
- **Stage 3 — done.** Turned the raw street-segment data into an actual
  connected walking network — the streets and pavements someone would walk
  along, not a straight line through buildings. Along the way we found (and
  fixed) a real gap: some street junctions in the official data don't quite
  line up with each other, which would have silently split the network into
  disconnected islands. Every existing venue and every candidate address
  from Stage 2 is now attached to its nearest point on this network, ready
  for the actual distance math in Stage 4.
- **Stages 4–6 — not started yet:** computing real walking distances and
  pass/fail per address, then the final map website.

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
links block scripted fetches (403). `scripts/03`–`06` pull Madrid's business
registry and build the walkable network graph; run them in numeric order
after 01/02, each depends on the previous ones' output.

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

All four are in scope for the pilot, and all four are confirmed present and
mapped (the official map service's description text only mentioned three of
them, which raised an early question about whether the fourth zone was
missing — it wasn't, that text was just outdated; see
`docs/data_sources.md`).

## Stages

1. **Ground truth the rule** — query ZPAE layer 4, extract `ZPAE` / `ZonaSupera` /
   `Normativa` per polygon for all four zones; parse the actual metre thresholds
   out of `Normativa` text (don't hardcode assumed numbers).
2. **Data pipeline** — ingest ZPAE polygons, censo de locales + terrazas (filtered
   to hostelería epígrafes), Catastro/Callejero address points. Reconcile CRS
   (native EPSG:25830).
3. **Network graph** — done. Built a Cityseer-compatible walkable graph
   from IGN/CNIG's IGR-RT street segments (filtered to exclude car tunnels,
   vehicle-only, and motorway-class segments; the node/relation table the
   original plan assumed doesn't exist in this download, so topology is
   built directly from segment geometry instead), decomposed to 10m
   resolution for accurate distance snapping. Existing hostelería locations
   and candidate address points from Stage 2 are snapped onto it. See
   `src/network.py` and `docs/data_sources.md`.
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
