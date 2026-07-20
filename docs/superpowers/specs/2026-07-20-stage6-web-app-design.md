# Stage 6: static web app — design

## Purpose

Stage 5 produced `data/processed/zpae_viability_map.geojson`: one Point
feature per evaluable candidate address (9,838 total, EPSG:4326) with
strict/lenient pass/fail verdicts, margins, binding classifications, the
specific nearest competitor behind each verdict, and occupancy context.
Stage 6 turns that (plus the original zoning-rule source layers) into the
actual map website described in the README: "click any building in one of
the four zones and see pass/fail, plus *why*."

## Non-goals

- No backend, no live queries — everything is precomputed static data
  (GeoJSON/PMTiles) served as static files.
- No coverage outside the four ZPAE zones — out of scope for the whole
  project, not just this stage.
- No automated UI/browser test suite — this repo has no JS test tooling
  and the interactions are small enough to verify by hand.

## Scope

Two data layers, both derived from files already on disk:

1. **Candidate viability layer** (the main layer): all 9,838 features from
   `zpae_viability_map.geojson`.
2. **Regulatory source layer** (new, supporting context): the original
   zoning inputs the pass/fail math is built on —
   `data/raw/zpae/zpae_ambitos.geojson` (4 zone boundary polygons) and
   `data/raw/zpae/zpae_clasificacion.geojson` (3,241 street-segment
   classification lines, `Clasifica` = alta/moderada/baja/sin superación).
   Both are currently EPSG:25830 and need reprojecting to EPSG:4326 for
   the web layer, same as Stage 5 did for the candidate layer.

## Architecture

Two new orchestration scripts (following the existing `scripts/`
orchestration vs `src/` logic split), a new `src/web_layer.py` function
for reprojection reuse, and a new `web/` directory holding the static
site itself.

### `scripts/10_build_regulatory_layer.py` (new)

Loads `zpae_ambitos.geojson` and `zpae_clasificacion.geojson`, reprojects
both from EPSG:25830 to EPSG:4326, writes:

- `web/data/zpae_zones.geojson` (~15KB, 4 polygon features)
- `web/data/zpae_streets.geojson` (~2MB, 3,241 line features)

Small enough that neither needs tiling — served as plain static GeoJSON,
loaded directly by MapLibre as GeoJSON sources.

### `scripts/11_build_vector_tiles.py` (new; the candidate layer)

Orchestrates:

1. Load `zpae_viability_map.geojson`.
2. Trim to the properties actually needed by the map/popups (drop the
   redundant EPSG:25830 `x`/`y` competitor-location columns now that
   `_lon`/`_lat` companions exist from Stage 5 — the web layer only needs
   the web-projected pair).
3. Shell out to `tippecanoe` to build `web/data/zpae.pmtiles` from the
   trimmed GeoJSON.
4. Emit `web/data/search_index.json`: a minimal array of
   `{id_porpk, address, lon, lat}` for the search bar (a few hundred KB,
   not tiled).

Fails loudly up front if `tippecanoe` is not on `PATH`, or if the input
GeoJSON is missing — same fail-loud convention as Stage 5's
competitor-column check.

### `src/web_layer.py` (extended)

New pure functions, unit tested alongside the existing ones:

```python
def reproject_geojson_layer(
    features: list[dict], source_crs: str
) -> list[dict]:
    """Reproject a list of GeoJSON features' geometry coordinates from
    source_crs to EPSG:4326, preserving properties untouched. Used for
    both zpae_ambitos and zpae_clasificacion."""

def trim_candidate_properties(properties: dict) -> dict:
    """Drop the EPSG:25830 x/y competitor-location columns now redundant
    with their _lon/_lat companions, returning the trimmed property dict
    used for the web tileset."""
```

### `web/` (new static site)

- `index.html`, `app.js`, `style.css` — vanilla JS, MapLibre GL (via CDN
  or vendored), the `pmtiles` JS plugin for reading `zpae.pmtiles` via
  HTTP range requests. No build step, no framework.
- `web/data/` — the four generated static assets:
  `zpae.pmtiles`, `search_index.json`, `zpae_zones.geojson`,
  `zpae_streets.geojson`. Generated, not committed to `main` (same
  gitignore convention as other pipeline outputs).

## Map behavior

- **Candidate points**: colored by verdict — green (pass) / red (fail) /
  grey (`prohibited_outright`). A **strict/lenient toggle** switches which
  verdict drives the coloring (paint-property swap, no data reload); the
  two differ on only 32 of 9,838 addresses per Stage 4, but both are
  first-class, not one buried in a popup.
- **Click a candidate point** → popup: address, verdict (per current
  toggle state), margin, zone, classification, and the specific blocking
  competitor (name, activity type, distance).
- **Search bar**: free-text substring match against `search_index.json`'s
  `address` field; selecting a match flies the map to it and opens its
  popup.
- **Regulatory layer toggle** (checkbox, off by default, labeled "Show
  zoning rules"): reveals `zpae_zones.geojson` as subtle zone outlines and
  `zpae_streets.geojson` as street segments colored by `Clasifica`, using
  a color ramp distinct from the pass/fail green/red (e.g. a
  yellow→orange→red loudness ramp) so both layers stay visually separable
  when shown together. Clicking a street segment (when visible) pops up
  its classification and zone.

## Error handling

- **Build-time**: `scripts/11_build_vector_tiles.py` checks `tippecanoe`
  is on `PATH` and the input GeoJSON exists before doing any work, failing
  loudly (not silently skipping) otherwise.
- **Client-side**: if any of the four `web/data/*` assets fails to load,
  show a plain error message in the map container rather than a silently
  blank map.

## Testing

Unit tests in `tests/test_web_layer.py` (extending the existing file):

- `reproject_geojson_layer`: a known EPSG:25830 coordinate reprojects to
  the expected EPSG:4326 lon/lat within a small tolerance; properties pass
  through unchanged.
- `trim_candidate_properties`: the redundant `x`/`y` columns are dropped;
  the `_lon`/`_lat` companions and all other properties are preserved.

No automated tests for `app.js` — no existing JS test tooling in this
repo, and the map/search/toggle interactions are small enough to verify
by hand in-browser (golden path: load map, toggle strict/lenient, search
an address, toggle regulatory layer, click a candidate point and a street
segment).

## Deployment

GitHub Actions workflow (`.github/workflows/deploy.yml`): on push to
`main`, installs `tippecanoe`, runs `scripts/10_build_regulatory_layer.py`
and `scripts/11_build_vector_tiles.py` to regenerate `web/data/*`, then
publishes `web/` via `actions/deploy-pages` to GitHub Pages. The generated
data files are build artifacts, not committed to `main`, consistent with
how every other pipeline output in this repo is treated.
