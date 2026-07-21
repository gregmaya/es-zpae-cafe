# Stage 6: Static Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the final map website — a static, no-backend page that
shows every evaluable candidate address colored pass/fail (strict/lenient
toggle), with a search bar, click-for-detail popups, and a toggleable
overlay of the original zoning regulation data (zone boundaries + street
noise classifications).

**Architecture:** Two new Python orchestration scripts
(`scripts/10_build_regulatory_layer.py`, `scripts/11_build_vector_tiles.py`)
turn Stage 5's output plus the raw ZPAE source layers into static web
assets under `web/data/` (a PMTiles archive for the 9,838 candidate
points, two small GeoJSON files for the regulatory layer, one small JSON
search index). A vanilla-JS, no-build-step site under `web/` (MapLibre GL
+ CARTO Positron basemap + the `pmtiles` JS plugin) loads those assets
directly in-browser. `web/data/*` is committed to git (unlike `data/`)
because CI cannot regenerate it from the manually-sourced raw inputs.

**Tech Stack:** Python (geopandas, already a dependency), `tippecanoe`
(new local-only build dependency, Homebrew), MapLibre GL JS v5 + `pmtiles`
JS v3 (loaded via unpkg CDN, no npm/bundler), CARTO Positron (hosted
basemap, no API key).

## Global Constraints

- Follow the existing `scripts/` (orchestration) vs `src/` (pure, tested
  logic) split used by every prior stage.
- `web/data/*` is committed to git — an explicit exception to this repo's
  usual "derived data is gitignored" rule, per
  `docs/superpowers/specs/2026-07-20-stage6-web-app-design.md` (CI cannot
  regenerate it).
- No backend, no build step for the site itself — plain HTML/CSS/JS, no
  npm/webpack/vite.
- No automated browser/JS tests — this repo has no JS test tooling; JS
  changes are verified by hand against a documented checklist per task.
- Python changes follow TDD: failing test → minimal implementation →
  passing test, per this repo's existing `tests/test_web_layer.py` style.

---

### Task 1: `trim_candidate_properties` — drop redundant competitor x/y columns

**Files:**
- Modify: `src/web_layer.py`
- Test: `tests/test_web_layer.py`

**Interfaces:**
- Produces: `trim_candidate_properties(properties: dict) -> dict`, used by
  Task 4 (`scripts/11_build_vector_tiles.py`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web_layer.py`:

```python
from web_layer import trim_candidate_properties


def test_trim_candidate_properties_drops_redundant_xy_columns():
    properties = {
        "id_porpk": 1,
        "address": "Calle Arganzuela, 2",
        "strict_pass": True,
        "strict_nearest_binding_x": 440000.0,
        "strict_nearest_binding_y": 4474000.0,
        "strict_nearest_binding_lon": -3.71,
        "strict_nearest_binding_lat": 40.41,
        "lenient_nearest_binding_x": 440001.0,
        "lenient_nearest_binding_y": 4474001.0,
        "strict_nearest_overall_x": 440002.0,
        "strict_nearest_overall_y": 4474002.0,
        "lenient_nearest_overall_x": 440003.0,
        "lenient_nearest_overall_y": 4474003.0,
    }
    trimmed = trim_candidate_properties(properties)
    assert trimmed == {
        "id_porpk": 1,
        "address": "Calle Arganzuela, 2",
        "strict_pass": True,
        "strict_nearest_binding_lon": -3.71,
        "strict_nearest_binding_lat": 40.41,
    }


def test_trim_candidate_properties_missing_columns_is_a_noop():
    # Not every row has every competitor column populated (e.g. a null
    # binding lookup on a prohibited-outright address) -- must not raise
    # if an x/y key is simply absent from this particular properties dict.
    properties = {"id_porpk": 1, "address": "Plaza Colon"}
    assert trim_candidate_properties(properties) == properties
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_layer.py -k trim_candidate_properties -v`
Expected: FAIL with `ImportError: cannot import name 'trim_candidate_properties'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/web_layer.py`:

```python
_REDUNDANT_COMPETITOR_XY_COLUMNS = [
    f"{prefix}_{axis}"
    for prefix in (
        "strict_nearest_binding", "lenient_nearest_binding",
        "strict_nearest_overall", "lenient_nearest_overall",
    )
    for axis in ("x", "y")
]


def trim_candidate_properties(properties: dict) -> dict:
    """Drop the EPSG:25830 x/y competitor-location columns now redundant
    with their _lon/_lat companions (added by Stage 5's
    reproject_competitor_locations), returning the trimmed property dict
    used for the web tileset."""
    return {
        key: value for key, value in properties.items()
        if key not in _REDUNDANT_COMPETITOR_XY_COLUMNS
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_layer.py -k trim_candidate_properties -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/web_layer.py tests/test_web_layer.py
git commit -m "Add trim_candidate_properties for the Stage 6 web tileset"
```

---

### Task 2: `build_search_index` — extract the search bar's data

**Files:**
- Modify: `src/web_layer.py`
- Test: `tests/test_web_layer.py`

**Interfaces:**
- Consumes: nothing new — takes any `gpd.GeoDataFrame` with `id_porpk`,
  `address`, and Point geometry already in EPSG:4326.
- Produces: `build_search_index(gdf: gpd.GeoDataFrame) -> list[dict]`,
  used by Task 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web_layer.py`:

```python
from web_layer import build_search_index


def test_build_search_index_extracts_id_address_lon_lat():
    gdf = gpd.GeoDataFrame(
        {"id_porpk": [1, 2], "address": ["Calle Arganzuela, 2", "Plaza Colon"]},
        geometry=[Point(-3.71, 40.41), Point(-3.70, 40.42)],
        crs="EPSG:4326",
    )
    index = build_search_index(gdf)
    assert index == [
        {"id_porpk": 1, "address": "Calle Arganzuela, 2", "lon": -3.71, "lat": 40.41},
        {"id_porpk": 2, "address": "Plaza Colon", "lon": -3.70, "lat": 40.42},
    ]


def test_build_search_index_handles_null_address():
    # join_address_labels is a left join -- a row with no portal match
    # keeps a null address rather than being dropped (see Stage 5).
    gdf = gpd.GeoDataFrame(
        {"id_porpk": [1], "address": [None]},
        geometry=[Point(-3.71, 40.41)],
        crs="EPSG:4326",
    )
    index = build_search_index(gdf)
    assert index == [{"id_porpk": 1, "address": None, "lon": -3.71, "lat": 40.41}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_layer.py -k build_search_index -v`
Expected: FAIL with `ImportError: cannot import name 'build_search_index'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/web_layer.py`:

```python
def build_search_index(gdf: gpd.GeoDataFrame) -> list[dict]:
    """Build the {id_porpk, address, lon, lat} records for the search
    bar's client-side index, from an EPSG:4326 GeoDataFrame of Points."""
    return [
        {
            "id_porpk": row.id_porpk,
            "address": None if pd.isna(row.address) else row.address,
            "lon": row.geometry.x,
            "lat": row.geometry.y,
        }
        for row in gdf.itertuples()
    ]
```

This needs `import pandas as pd` added to the top of `src/web_layer.py`
alongside the existing `geopandas`/`pyproj` imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_layer.py -k build_search_index -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/web_layer.py tests/test_web_layer.py
git commit -m "Add build_search_index for the Stage 6 search bar"
```

---

### Task 3: `scripts/10_build_regulatory_layer.py` — reproject zone + street layers

**Files:**
- Create: `scripts/10_build_regulatory_layer.py`
- Modify: `.gitignore` (add a `web/data/` exception to the blanket `data/` rule — see Step 4)

**Interfaces:**
- Consumes: `data/raw/zpae/zpae_ambitos.geojson`,
  `data/raw/zpae/zpae_clasificacion.geojson` (both already on disk,
  confirmed EPSG:25830, read correctly by `geopandas.read_file`).
- Produces: `web/data/zpae_zones.geojson`, `web/data/zpae_streets.geojson`
  (both EPSG:4326), consumed by Task 9 (`app.js`'s regulatory layer).

- [ ] **Step 1: Write the script**

Create `scripts/10_build_regulatory_layer.py`:

```python
"""
Stage 6: reproject the two raw zoning-rule source layers (zone boundaries
and street noise classifications) to EPSG:4326 for the web app's
regulatory overlay. See
docs/superpowers/specs/2026-07-20-stage6-web-app-design.md.

Run locally:
    python scripts/10_build_regulatory_layer.py
"""

from pathlib import Path

import geopandas as gpd

RAW_ZPAE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "zpae"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"

WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

zones = gpd.read_file(RAW_ZPAE_DIR / "zpae_ambitos.geojson")
assert zones.crs is not None and zones.crs.to_epsg() == 25830, (
    f"Expected zpae_ambitos.geojson in EPSG:25830, got {zones.crs}"
)
zones = zones.to_crs("EPSG:4326")
zones.to_file(WEB_DATA_DIR / "zpae_zones.geojson", driver="GeoJSON")
print(f"Saved {len(zones)} zone polygons to {WEB_DATA_DIR / 'zpae_zones.geojson'}")

streets = gpd.read_file(RAW_ZPAE_DIR / "zpae_clasificacion.geojson")
assert streets.crs is not None and streets.crs.to_epsg() == 25830, (
    f"Expected zpae_clasificacion.geojson in EPSG:25830, got {streets.crs}"
)
streets = streets.to_crs("EPSG:4326")
streets.to_file(WEB_DATA_DIR / "zpae_streets.geojson", driver="GeoJSON")
print(f"Saved {len(streets)} street segments to {WEB_DATA_DIR / 'zpae_streets.geojson'}")
```

- [ ] **Step 2: Run it**

Run: `source .venv/bin/activate && python scripts/10_build_regulatory_layer.py`
Expected output:
```
Saved 4 zone polygons to .../web/data/zpae_zones.geojson
Saved 3241 street segments to .../web/data/zpae_streets.geojson
```

- [ ] **Step 3: Verify the output**

Run:
```bash
python3 -c "
import json
z = json.load(open('web/data/zpae_zones.geojson'))
s = json.load(open('web/data/zpae_streets.geojson'))
assert len(z['features']) == 4
assert len(s['features']) == 3241
lon, lat = z['features'][0]['geometry']['coordinates'][0][0]
assert -4 < lon < -3, lon   # Madrid longitude sanity check
assert 40 < lat < 41, lat   # Madrid latitude sanity check
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: Update `.gitignore` so `web/data/` is not swept up by the blanket `data/` rule**

`web/data/` is a different directory from the gitignored `data/` at repo
root, so no change is actually needed for that — Python's `Path` and
git's pattern matching both treat `data/` (no leading slash, matches any
directory named `data` at any depth) as matching `web/data/` too. Confirm
this and fix it:

Run: `git check-ignore -v web/data/zpae_zones.geojson`
Expected: prints a match against the `data/` line in `.gitignore` —
confirming it WOULD be ignored unless fixed.

Edit `.gitignore`'s `data/` line to be root-anchored so it stops matching
`web/data/`:

```diff
-# All downloaded/derived GIS data -- large, regenerable via scripts/*.py.
-data/
+# All downloaded/derived GIS data -- large, regenerable via scripts/*.py.
+/data/
```

Run: `git check-ignore -v web/data/zpae_zones.geojson`
Expected: no output (exit code 1) — no longer ignored.

Run: `git check-ignore -v data/processed/zpae_viability_map.geojson`
Expected: still prints a match — the root `data/` is still ignored.

- [ ] **Step 5: Commit**

```bash
git add scripts/10_build_regulatory_layer.py .gitignore web/data/zpae_zones.geojson web/data/zpae_streets.geojson
git commit -m "Add Stage 6 regulatory layer build script"
```

---

### Task 4: `scripts/11_build_vector_tiles.py` — candidate points to PMTiles + search index

**Files:**
- Create: `scripts/11_build_vector_tiles.py`

**Interfaces:**
- Consumes: `data/processed/zpae_viability_map.geojson` (Stage 5 output,
  already on disk), `trim_candidate_properties` and `build_search_index`
  from Task 1/2.
- Produces: `web/data/zpae.pmtiles` (vector tileset, source-layer name
  `candidates`), `web/data/search_index.json` — both consumed by the
  `app.js` tasks below.

- [ ] **Step 1: Install tippecanoe**

Run: `brew install tippecanoe`
Run: `tippecanoe --version`
Expected: prints a version string (confirms it's on `PATH`).

- [ ] **Step 2: Write the script**

Create `scripts/11_build_vector_tiles.py`:

```python
"""
Stage 6: convert Stage 5's candidate viability layer into a PMTiles vector
tileset for the web app, plus a small search index for the address search
bar. See docs/superpowers/specs/2026-07-20-stage6-web-app-design.md.

Requires tippecanoe on PATH (`brew install tippecanoe`).

Run locally:
    python scripts/11_build_vector_tiles.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from web_layer import build_search_index, trim_candidate_properties

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
INPUT_PATH = PROCESSED_DIR / "zpae_viability_map.geojson"

if shutil.which("tippecanoe") is None:
    raise RuntimeError(
        "tippecanoe is not on PATH -- install it first (`brew install "
        "tippecanoe`) before running this script."
    )

if not INPUT_PATH.exists():
    raise RuntimeError(
        f"{INPUT_PATH} not found -- run scripts/09_build_web_layer.py "
        f"first to produce Stage 5's output."
    )

WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

candidates = gpd.read_file(INPUT_PATH)
print(f"Loaded {len(candidates)} candidates.")

search_index = build_search_index(candidates)
search_index_path = WEB_DATA_DIR / "search_index.json"
search_index_path.write_text(json.dumps(search_index))
print(f"Saved {len(search_index)} search index entries to {search_index_path}")

trimmed = json.loads(candidates.to_json())
for feature in trimmed["features"]:
    feature["properties"] = trim_candidate_properties(feature["properties"])

pmtiles_path = WEB_DATA_DIR / "zpae.pmtiles"
result = subprocess.run(
    [
        "tippecanoe",
        "-f",
        "-o", str(pmtiles_path),
        "-l", "candidates",
        "-zg",
        "--drop-densest-as-needed",
    ],
    input=json.dumps(trimmed).encode("utf-8"),
    capture_output=True,
)
if result.returncode != 0:
    raise RuntimeError(
        f"tippecanoe failed (exit {result.returncode}):\n"
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )
print(result.stderr.decode("utf-8", errors="replace"))
print(f"Saved vector tileset to {pmtiles_path}")
```

- [ ] **Step 3: Run it**

Run: `source .venv/bin/activate && python scripts/11_build_vector_tiles.py`
Expected: prints `Loaded 9838 candidates.`, tippecanoe's own progress
output (feature/tile counts), and `Saved vector tileset to
.../web/data/zpae.pmtiles`.

- [ ] **Step 4: Verify the output**

Run:
```bash
python3 -c "
import json
from pathlib import Path
idx = json.load(open('web/data/search_index.json'))
assert len(idx) == 9838
assert set(idx[0].keys()) == {'id_porpk', 'address', 'lon', 'lat'}
size = Path('web/data/zpae.pmtiles').stat().st_size
assert size > 1_000_000, f'pmtiles suspiciously small: {size} bytes'
print('OK', size, 'bytes')
"
```
Expected: `OK <some size> bytes` with no assertion errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/11_build_vector_tiles.py web/data/zpae.pmtiles web/data/search_index.json
git commit -m "Add Stage 6 vector tile + search index build script"
```

---

### Task 5: `web/` scaffold — basemap loads

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js`

**Interfaces:**
- Produces: a working MapLibre `Map` instance assigned to a module-level
  `map` variable in `app.js`, centered on Madrid, with the CARTO Positron
  basemap — consumed by every later task in this plan.

- [ ] **Step 1: Write `web/index.html`**

Create `web/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>ZPAE Café Viability Map</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.css" />
<link rel="stylesheet" href="style.css" />
</head>
<body>
<div id="map"></div>
<div id="controls">
  <div id="search-box">
    <input id="search-input" type="text" placeholder="Search address…" autocomplete="off" />
    <ul id="search-results"></ul>
  </div>
  <div id="toggles">
    <label><input type="checkbox" id="verdict-toggle" /> Lenient verdict</label>
    <label><input type="checkbox" id="disagreement-toggle" /> Highlight strict/lenient disagreements</label>
    <label><input type="checkbox" id="regulatory-toggle" /> Show zoning rules</label>
  </div>
</div>
<div id="error-banner" hidden></div>
<script src="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@^3/dist/pmtiles.js"></script>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/style.css`**

Create `web/style.css`:

```css
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: system-ui, sans-serif;
}

#map {
  position: absolute;
  inset: 0;
}

#controls {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

#search-box {
  position: relative;
  width: 280px;
}

#search-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 14px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

#search-results {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  background: white;
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  max-height: 240px;
  overflow-y: auto;
}

#search-results:empty {
  display: none;
}

#search-results li {
  padding: 8px 10px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid #eee;
}

#search-results li:hover {
  background: #f2f2f2;
}

#toggles {
  background: white;
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  padding: 8px 10px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

#error-banner {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  background: #b91c1c;
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 14px;
}
```

- [ ] **Step 3: Write the map-initialization part of `web/app.js`**

Create `web/app.js`:

```javascript
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [-3.7038, 40.4168],
  zoom: 13,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");
```

- [ ] **Step 4: Verify in browser**

Run: `cd web && python3 -m http.server 8000`
Open `http://localhost:8000` in a browser.
Expected: a light-grey minimal basemap of central Madrid loads, with zoom
controls in the top-right and the (currently non-functional) search box
and toggle checkboxes visible in the top-left. No console errors.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/style.css web/app.js
git commit -m "Scaffold Stage 6 web app with CARTO Positron basemap"
```

---

### Task 6: candidate points layer — colors + click popup

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `map` from Task 5; `web/data/zpae.pmtiles` (source-layer
  `candidates`) from Task 4.
- Produces: a module-level `currentVerdictPrefix` variable (`"strict"` or
  `"lenient"`, starts `"strict"`) and a `buildPopupHTML(properties)`
  function — both consumed by Task 7 (verdict toggle) and Task 8 (search).

- [ ] **Step 1: Add the candidate layer and popup logic**

Append to `web/app.js`:

```javascript
let currentVerdictPrefix = "strict";

function verdictColorExpression(prefix) {
  return [
    "case",
    ["==", ["get", "prohibited_outright"], true], "#6b7280",
    ["==", ["get", `${prefix}_pass`], true], "#16a34a",
    "#dc2626",
  ];
}

function buildPopupHTML(properties) {
  const prefix = currentVerdictPrefix;
  const pass = properties[`${prefix}_pass`];
  const margin = properties[`${prefix}_margin_m`];
  const verdictText = properties.prohibited_outright
    ? "Prohibited outright (Alta street)"
    : pass
      ? `Pass (margin ${Number(margin).toFixed(1)}m)`
      : `Fail (short by ${Math.abs(Number(margin)).toFixed(1)}m)`;

  const bindingRotulo = properties[`${prefix}_nearest_binding_rotulo`];
  const overallRotulo = properties[`${prefix}_nearest_overall_rotulo`];
  const competitorRotulo = bindingRotulo || overallRotulo;
  const competitorDistance = bindingRotulo
    ? properties[`${prefix}_nearest_binding_distance_m`]
    : properties[`${prefix}_nearest_overall_distance_m`];
  const competitorLine = competitorRotulo
    ? `<p>Nearest: ${competitorRotulo} (${Number(competitorDistance).toFixed(1)}m)</p>`
    : "";

  return `
    <strong>${properties.address ?? "Unknown address"}</strong>
    <p>${properties.zpae_zone} — ${properties.classification} street</p>
    <p>${verdictText}</p>
    ${competitorLine}
  `;
}

map.on("load", () => {
  map.addSource("candidates", {
    type: "vector",
    url: "pmtiles://data/zpae.pmtiles",
  });

  map.addLayer({
    id: "candidate-points",
    type: "circle",
    source: "candidates",
    "source-layer": "candidates",
    paint: {
      "circle-radius": 5,
      "circle-color": verdictColorExpression(currentVerdictPrefix),
      "circle-stroke-width": 1,
      "circle-stroke-color": "#ffffff",
    },
  });

  map.on("click", "candidate-points", (e) => {
    const properties = e.features[0].properties;
    new maplibregl.Popup()
      .setLngLat(e.lngLat)
      .setHTML(buildPopupHTML(properties))
      .addTo(map);
  });

  map.on("mouseenter", "candidate-points", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "candidate-points", () => {
    map.getCanvas().style.cursor = "";
  });
});
```

- [ ] **Step 2: Verify in browser**

Refresh `http://localhost:8000` (server from Task 5 still running).
Expected: colored dots (green/red/grey) appear across the four ZPAE
zones. Clicking a dot opens a popup with its address, zone, verdict, and
(where applicable) the nearest competitor. No console errors.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "Add candidate points layer with verdict colors and popups"
```

---

### Task 7: strict/lenient verdict toggle

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `currentVerdictPrefix`, `verdictColorExpression` from Task 6.

- [ ] **Step 1: Wire up the toggle**

Append to `web/app.js`:

```javascript
document.getElementById("verdict-toggle").addEventListener("change", (e) => {
  currentVerdictPrefix = e.target.checked ? "lenient" : "strict";
  if (map.getLayer("candidate-points")) {
    map.setPaintProperty(
      "candidate-points",
      "circle-color",
      verdictColorExpression(currentVerdictPrefix)
    );
  }
});
```

- [ ] **Step 2: Verify in browser**

Refresh the page. Check the "Lenient verdict" checkbox.
Expected: marker colors update immediately (a small number of markers —
up to 32 per the Stage 4 findings — may flip red/green). Click a marker
after toggling: the popup's verdict text reflects the lenient result, not
strict. Uncheck: colors and popups revert to strict.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "Add strict/lenient verdict toggle"
```

---

### Task 8: address search bar

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `web/data/search_index.json` from Task 4; `map`,
  `buildPopupHTML` from Task 6.

- [ ] **Step 1: Add search logic**

Append to `web/app.js`:

```javascript
let searchIndex = [];

fetch("data/search_index.json")
  .then((r) => {
    if (!r.ok) throw new Error(`search_index.json: HTTP ${r.status}`);
    return r.json();
  })
  .then((data) => {
    searchIndex = data;
  })
  .catch((err) => showError(`Failed to load search index: ${err.message}`));

const searchInput = document.getElementById("search-input");
const searchResults = document.getElementById("search-results");

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim().toLowerCase();
  searchResults.innerHTML = "";
  if (query.length < 3) return;

  const matches = searchIndex
    .filter((entry) => entry.address && entry.address.toLowerCase().includes(query))
    .slice(0, 10);

  for (const match of matches) {
    const li = document.createElement("li");
    li.textContent = match.address;
    li.addEventListener("click", () => selectSearchResult(match));
    searchResults.appendChild(li);
  }
});

function selectSearchResult(match) {
  searchResults.innerHTML = "";
  searchInput.value = match.address;
  map.flyTo({ center: [match.lon, match.lat], zoom: 18 });

  map.once("idle", () => {
    const point = map.project([match.lon, match.lat]);
    const features = map.queryRenderedFeatures(
      [
        [point.x - 6, point.y - 6],
        [point.x + 6, point.y + 6],
      ],
      { layers: ["candidate-points"] }
    );
    const feature = features.find((f) => f.properties.id_porpk === match.id_porpk);
    if (feature) {
      new maplibregl.Popup()
        .setLngLat([match.lon, match.lat])
        .setHTML(buildPopupHTML(feature.properties))
        .addTo(map);
    }
  });
}
```

- [ ] **Step 2: Verify in browser**

Refresh the page. Type a partial address known to exist (e.g. "arganzuela"
or any street visible on the loaded map) into the search box.
Expected: a dropdown list of up to 10 matching addresses appears.
Clicking one flies the map to that address at zoom 18 and opens its
popup. Typing fewer than 3 characters shows no dropdown.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "Add address search bar"
```

---

### Task 9: regulatory layer (zone boundaries + street classifications)

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `web/data/zpae_zones.geojson`, `web/data/zpae_streets.geojson`
  from Task 3; `map` from Task 5.

- [ ] **Step 1: Add the regulatory layers, hidden by default**

Append to the `map.on("load", ...)` callback body in `web/app.js` (inside
the existing callback added in Task 6, after the `candidate-points` layer
and its handlers):

```javascript
  map.addSource("zpae-zones", { type: "geojson", data: "data/zpae_zones.geojson" });
  map.addSource("zpae-streets", { type: "geojson", data: "data/zpae_streets.geojson" });

  map.addLayer({
    id: "zpae-zone-outline",
    type: "line",
    source: "zpae-zones",
    layout: { visibility: "none" },
    paint: { "line-color": "#374151", "line-width": 2, "line-dasharray": [2, 2] },
  });

  map.addLayer({
    id: "zpae-street-classification",
    type: "line",
    source: "zpae-streets",
    layout: { visibility: "none" },
    paint: {
      "line-width": 3,
      "line-color": [
        "match",
        ["get", "Clasifica"],
        "Alta", "#dc2626",
        "Moderada", "#f97316",
        "Baja", "#eab308",
        "#9ca3af",
      ],
    },
  });

  map.on("click", "zpae-street-classification", (e) => {
    const p = e.features[0].properties;
    new maplibregl.Popup()
      .setLngLat(e.lngLat)
      .setHTML(`<strong>${p.ZPAE}</strong><p>Classification: ${p.Clasifica}</p>`)
      .addTo(map);
  });
```

- [ ] **Step 2: Wire up the toggle**

Append to `web/app.js` (outside the `map.on("load", ...)` callback):

```javascript
document.getElementById("regulatory-toggle").addEventListener("change", (e) => {
  const visibility = e.target.checked ? "visible" : "none";
  for (const layerId of ["zpae-zone-outline", "zpae-street-classification"]) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visibility);
    }
  }
});
```

- [ ] **Step 3: Verify in browser**

Refresh the page. Check "Show zoning rules".
Expected: dashed zone-boundary outlines and colored street segments
(red/orange/yellow/grey by classification) appear on top of the basemap,
distinct in color from the green/red candidate dots. Clicking a colored
street segment opens a popup with its zone and classification. Unchecking
the box hides both layers again.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "Add toggleable regulatory layer (zones + street classifications)"
```

---

### Task 10: client-side error handling for failed asset loads

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Produces: `showError(message)`, used by Task 8's existing `.catch()`
  and newly wired into the PMTiles/GeoJSON source error paths.

- [ ] **Step 1: Add `showError` and wire it into asset loading**

Add near the top of `web/app.js` (before its first use — reorder so this
appears above the Task 8 `fetch(...).catch(...)` call, which already
references it):

```javascript
function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.hidden = false;
}
```

Append to `web/app.js`, after the `map.on("load", ...)` block:

```javascript
map.on("error", (e) => {
  const sourceId = e.sourceId || "unknown source";
  showError(`Failed to load map layer (${sourceId}): ${e.error?.message ?? "unknown error"}`);
});
```

- [ ] **Step 2: Verify in browser**

Temporarily rename `web/data/zpae.pmtiles` to `web/data/zpae.pmtiles.bak`,
refresh the page.
Expected: a red error banner appears at the top of the page reporting the
failed layer, rather than a silently blank/broken map.
Restore the file: rename it back to `web/data/zpae.pmtiles`. Refresh again
and confirm the banner is gone and the map loads normally.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "Add client-side error banner for failed asset loads"
```

---

### Task 11: strict/lenient disagreement highlight

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `map` from Task 5; `candidates` source (source-layer
  `candidates`) added in Task 6; the `interpretations_disagree` boolean
  property already present on every candidate feature (untouched by
  `trim_candidate_properties`, which only drops the 8 redundant x/y
  columns).

- [ ] **Step 1: Add the highlight layer, hidden by default**

Append to the `map.on("load", ...)` callback body in `web/app.js`, after
the `candidate-points` layer and its click/hover handlers added in Task 6
(so the halo layer draws on top of the points it's highlighting):

```javascript
  map.addLayer({
    id: "candidate-disagreement-highlight",
    type: "circle",
    source: "candidates",
    "source-layer": "candidates",
    filter: ["==", ["get", "interpretations_disagree"], true],
    layout: { visibility: "none" },
    paint: {
      "circle-radius": 9,
      "circle-color": "transparent",
      "circle-stroke-width": 3,
      "circle-stroke-color": "#7c3aed",
    },
  });
```

- [ ] **Step 2: Wire up the toggle**

Append to `web/app.js` (outside the `map.on("load", ...)` callback, near
the other toggle listeners from Tasks 7 and 9):

```javascript
document.getElementById("disagreement-toggle").addEventListener("change", (e) => {
  if (map.getLayer("candidate-disagreement-highlight")) {
    map.setLayoutProperty(
      "candidate-disagreement-highlight",
      "visibility",
      e.target.checked ? "visible" : "none"
    );
  }
});
```

- [ ] **Step 3: Verify in browser**

Refresh the page. Check "Highlight strict/lenient disagreements".
Expected: a purple ring (halo) appears around a small number of markers
(32 across the whole dataset, per Stage 4's findings) — everything else
stays visible and unchanged, so the outliers are visible in their full
geographic context (e.g. whether they cluster in one zone or scatter
across all four). Toggling strict/lenient (Task 7) while this is on
doesn't change which markers are highlighted — `interpretations_disagree`
is the same regardless of which verdict is currently displayed.
Unchecking the box removes the halos.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "Add strict/lenient disagreement highlight toggle"
```

---

### Task 12: GitHub Pages deployment workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: the committed `web/` directory (including `web/data/*` from
  Tasks 3–4) — no data regeneration in CI, per the Deployment section of
  the design spec.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy web app to GitHub Pages

on:
  push:
    branches: [main]
    paths: ["web/**"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: web
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Enable GitHub Pages for the repo**

In the repo's GitHub settings → Pages, set the source to "GitHub Actions"
(this is a one-time manual setting, not something the workflow file
itself can configure).

- [ ] **Step 3: Verify**

Push this commit to `main` (or run the workflow manually via
`workflow_dispatch` from the Actions tab).
Expected: the "Deploy web app to GitHub Pages" workflow run succeeds, and
the reported Pages URL serves the working map (same behavior as the local
`http://localhost:8000` checks in Tasks 5–10).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "Add GitHub Pages deployment workflow for the web app"
```
