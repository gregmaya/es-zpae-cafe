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

## What this actually does, in plain English

Madrid has four small neighbourhoods (Centro, Gaztambide, AZCA-Av. de Brasil,
Trafalgar-Ríos Rosas) that are officially "saturated" with noise — the city
has designated them Zonas de Protección Acústica Especial (ZPAE) — and each
one has its own local law restricting *where* a new bar or café can open. The
rule isn't "no new bars" — it's "a new bar has to be a certain distance away
from the nearest existing bar/nightclub/restaurant," and that minimum
distance depends on how loud the street is officially rated. So the same
empty shop unit might be a legal spot for a café or an illegal one, purely
based on what's already nearby and how loud both streets are rated.

This tool answers that question automatically, for every address in those
four zones: **if you tried to open a café/bar here, would the council
actually let you, based purely on distance to existing venues?** It does
that by combining four official government datasets (the noise-zone maps,
the business registry, the street network, and the address registry) and
running the actual legal distance rule against real walking distances —
not straight-line "as the crow flies" distances, since the law explicitly
requires distance measured along the street, door to door.

The end product (not built yet — see Stages 5-6 below) is a static map:
click any building in one of the four zones and see pass/fail, plus *why*
— which specific existing venue is too close, and by how much.

## Findings and legal interpretations we had to make

The law here is not a simple lookup table, and reading the actual council
documents (not summaries) surfaced several things worth calling out
explicitly rather than burying in code comments:

- **The rule is asymmetric and two-sided.** The minimum distance depends on
  *both* how loud the new café's own street is rated *and* how loud the
  existing competitor's street is rated — these aren't the same number. In
  Trafalgar-Ríos Rosas, for example, a café on a "Baja" (quiet) street needs
  150m from a competitor on an "Alta" (loud) street, but a café on a
  "Moderada" street only needs 100m from that same competitor. See
  [`src/zones.py`](src/zones.py) for the full rule table per zone.
- **One zone's extra rule turned out to be legally dead.** Centro's
  Normativa document contains an Article 21 imposing an additional
  zone-boundary distance rule — but it's struck through in the official PDF
  with a footnote citing a 2022 Tribunal Superior de Justicia de Madrid
  ruling that annulled it. We treat it as void, not as an open question.
- **"Which venues count as competitors" isn't just "other cafés."** The law
  is written in terms of a 1998 noise-classification decree (Decreto
  184/1998), which sweeps in restaurants, bars, cafeterías, nightclubs,
  live-music venues, and banquet halls — but explicitly *not* gyms, pools,
  theatres, museums, or hotel accommodation (even though a hotel can have a
  street-facing bar — the business registry doesn't record that distinction,
  so we exclude it rather than guess). See [`src/activities.py`](src/activities.py).
- **"Loud music" carve-outs aren't uniform across zones.** Three of the four
  zones ban *any* café/bar with live music outright in "Moderada" streets;
  AZCA's outright ban is narrower — only restaurants with live music
  specifically, not the whole music-venue category. This project models
  the plain (no live music) case throughout, since that's the common one.
- **Sound-street classification, not distance, is the hard stop in most
  zones.** Three of the four zones flatly ban *any* new café/bar on their
  loudest ("Alta") streets, no matter how far from anything else — distance
  never comes into it for those addresses. Of our 9,838 evaluable
  addresses, 1,939 fail this way.
- **The wording is ambiguous about the last few metres.** The law says
  distance is measured door-to-door along the street — but doesn't say
  whether that includes the short walk from a building's actual front door
  out to the public street itself. Rather than picking one reading, we
  computed the result both ways (see Stage 4 below); they agree on all but
  32 of 9,838 addresses.
- **Some numbers needed manual cross-checking against amendments.** A few
  zones had later modifications (BOAM bulletins) layered on top of their
  original text; one zone's amendment text didn't cleanly match the PDF we
  had, and rather than silently pick a number, we flagged the discrepancy
  in `src/zones.py` for anyone who needs that specific edge case resolved.

None of this is guesswork dressed up as certainty — every interpretation
above is sourced to the actual council PDF and documented at the point in
the code where it matters (`src/zones.py`, `src/activities.py`,
`docs/data_sources.md`), specifically so a reader can check our reading of
the law against the source rather than just trusting a summary.

## Status

**In plain terms: we know the actual rules, we've mapped where every bar,
café, and nightlife venue is in the four zones, we have an actual walkable
street network to measure distances over, and we've now actually run the
distance math for every candidate address.** Four stages down, two to go
before this becomes a usable map.

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
- **Stage 4 — done.** For every candidate address, measured the actual
  walking distance to the nearest existing café/bar of each street-loudness
  classification that matters for that address's zone, then used those
  distances (plus a margin) to work out a pass/fail. Because the rule's
  exact wording is a bit ambiguous about whether the walk from a building's
  front door out to the street should count, we computed it both ways —
  once including that short extra walk, once without — rather than quietly
  picking one reading. Each candidate's result now also identifies the
  specific nearest competitor (name, activity type, location) behind each
  distance figure, not just the number — so the eventual UI can explain
  *why* an address passes or fails, not just *whether*. Of the 13,876
  candidate addresses, 9,838 are both inside a ZPAE zone and close enough
  to a street with a known classification to be evaluable at all (the rest
  fall outside the zones' scope entirely). Of those, only about 1 in 8 —
  roughly 1,250 — actually clear the distance bar; 1,939 are banned
  outright no matter the distance, because they'd sit on the loudest
  ("Alta") kind of street, which three of the four zones forbid new
  hostelería on regardless of how far from anything else it is. The two
  ways of measuring distance agreed almost everywhere — only 32 out of
  9,838 addresses flipped between pass and fail depending on which
  convention was used.
- **Stage 5 — done.** Assembled the static `zpae_viability_map.geojson`
  output, ready for the map website to load directly: one Point feature per
  evaluable candidate (9,838 total) in EPSG:4326, with human-readable address
  labels, today's occupancy context (commercial/residential status, activity
  summary), and reprojects all nearest-competitor lookups' coordinates to
  web-friendly lon/lat pairs alongside their original EPSG:25830 coordinates.
- **Stage 6 — not started yet:** the final map website itself.

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
4. **Distance engine** — done. For every evaluable candidate address, computed
   network distance (not euclidean) to the nearest hostelería local of each
   relevant classification, evaluated against the classification-specific
   threshold for that street, pass/fail + margin in metres. Computed under
   two distance conventions (with and without the building-door-to-street
   offset, since the Normativa's wording doesn't cleanly resolve which one
   applies) rather than picking one silently. See `src/distance_engine.py`
   and `docs/data_sources.md`.
5. **Precompute** — run the engine over every address point in the four zones,
   bake to a static GeoJSON/vector-tile scoring layer.
6. **Web app** — Leaflet/MapLibre static site: building-by-building shading +
   address search, no backend. Deployable as static files (GitHub Pages or
   similar).

## Non-goals for v1
- No live Cityseer queries in the browser — everything precomputed offline.
- No coverage outside the four declared ZPAE polygons (outside them, no
  distance restriction applies at all under this rule).
