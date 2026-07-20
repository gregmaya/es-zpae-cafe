# Stage 5 Web Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble the single static file the eventual map website will load: one GeoJSON feature per evaluable candidate address (9,838 of them), in web-ready EPSG:4326, with a human-readable address label and today's occupancy context joined back in on top of Stage 4's pass/fail verdicts and competitor identities.

**Architecture:** A new module `src/web_layer.py` provides pure, testable functions — an address-label formatter and two left-join helpers (address labels, occupancy context) — plus a coordinate-reprojection helper for the nearest-competitor `x`/`y` columns (plain floats, not GeoDataFrame geometry, so they need their own `pyproj.Transformer` pass separate from the main geometry's `.to_crs()`). A new script `scripts/09_build_web_layer.py` orchestrates: load the three existing processed files, join, reproject, and write `data/processed/zpae_viability_map.geojson`.

**Tech Stack:** Python, GeoPandas, pyproj (3.7.2, confirmed installed), pytest.

## Global Constraints

- Scope is exactly the 9,838 rows already in `data/processed/distance_evaluation_results.gpkg` (already scoped to "inside a ZPAE zone AND matched to a classified street") — no additional filtering.
- `distance_evaluation_results.gpkg` on disk predates the nearest-competitor-identity addition and must be regenerated (`python scripts/08_compute_distances.py`) before Stage 5's script can consume the 28 competitor-identity columns. Stage 5's script must fail loudly (raise, not silently proceed) if those columns are missing.
- Join key is `id_porpk` throughout — confirmed unique (no duplicates) in `data/processed/rt_portalpk_p_zpae_clip.gpkg` (13,876 rows).
- `nombre` and `tvia` in `rt_portalpk_p_zpae_clip.gpkg` are UPPERCASE (e.g. `"ARGANZUELA"`, `"CALLE"`) — title-case them for the address label. `numero` is a string and is sometimes the literal placeholder `"Desconocido"` (confirmed present in the real data, e.g. `tvia="PLAZA", nombre="COLON", numero="Desconocido"`) — when `numero == "Desconocido"`, omit the number from the label rather than printing the placeholder. `tvia` is null for exactly 1 of 13,876 rows — handle a null `tvia` by falling back to just the (title-cased) `nombre`.
- `current_activity_summary` in `candidate_addresses_zpae_tagged.gpkg` round-trips through GPKG as a JSON-encoded *string* (e.g. `'[{"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}]'`) because GPKG can't hold nested types. Parse it back into a real Python list-of-dicts (`json.loads`) before it reaches the final GeoJSON, so consumers get proper nested JSON, not a double-encoded string.
- Source CRS is EPSG:25830 throughout (confirmed on all three input files); target CRS for the web layer is EPSG:4326, per the project's stated web-layer convention (see `src/zpae_geometry.py:TARGET_CRS` for the equivalent EPSG:25830 constant pattern this mirrors).
- New module lives at `src/web_layer.py`; new script at `scripts/09_build_web_layer.py` (next number after Stage 4's `08_compute_distances.py`), following the existing `src/` (logic) vs `scripts/` (orchestration) split.
- Tests go in `tests/test_web_layer.py`, following the existing test style (plain `geopandas` fixtures built inline, no shared fixture files — see `tests/test_distance_engine.py`, `tests/test_network.py`).
- Data files referenced (`data/processed/*.gpkg`) are gitignored and not present in a fresh worktree/checkout — Task 4's real-data smoke test can only run in an environment where Stage 1-4 have actually been executed locally (confirmed present in the primary checkout at `/Users/nfi/dev/es-zpae-cafe`, absent in a fresh worktree branched from `origin/main`). Tasks 1-3 are fully verifiable via unit tests with synthetic fixtures regardless of environment.

---

## Task 1: `build_address_label`

**Files:**
- Create: `src/web_layer.py`
- Test: `tests/test_web_layer.py`

**Interfaces:**
- Produces: `build_address_label(tvia: str | None, nombre: str, numero: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
from web_layer import build_address_label


def test_build_address_label_normal_case():
    assert build_address_label("CALLE", "ARGANZUELA", "2") == "Calle Arganzuela, 2"


def test_build_address_label_omits_unknown_numero():
    # Real data contains numero == "Desconocido" as a placeholder for an
    # unknown house number (e.g. PLAZA COLON) -- must not print the
    # placeholder verbatim.
    assert build_address_label("PLAZA", "COLON", "Desconocido") == "Plaza Colon"


def test_build_address_label_handles_null_tvia():
    # tvia is null for a small number of real rows -- fall back to just
    # the street name.
    assert build_address_label(None, "GRAN VIA", "10") == "Gran Via, 10"


def test_build_address_label_null_tvia_and_unknown_numero():
    assert build_address_label(None, "GRAN VIA", "Desconocido") == "Gran Via"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_layer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'web_layer'`

- [ ] **Step 3: Write minimal implementation**

```python
"""
Assembles Stage 5's static web layer: joins Stage 4's pass/fail +
competitor-identity results with a human-readable address label (from
Stage 2's raw portal-point pull) and today's occupancy context (from
Stage 2/7's tagged candidate addresses), then reprojects everything to
EPSG:4326 for the web. See
docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md.
"""

import json

import geopandas as gpd
from pyproj import Transformer


def build_address_label(tvia: str | None, nombre: str, numero: str) -> str:
    """Build a human-readable address label, e.g.
    ("CALLE", "ARGANZUELA", "2") -> "Calle Arganzuela, 2". numero ==
    "Desconocido" (a real placeholder in the source data for an unknown
    house number) is omitted rather than printed verbatim. A null tvia
    (present for a small number of real rows) falls back to just the
    street name."""
    street = nombre.title()
    if tvia:
        street = f"{tvia.title()} {street}"
    if numero and numero != "Desconocido":
        return f"{street}, {numero}"
    return street
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_layer.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/web_layer.py tests/test_web_layer.py
git commit -m "Add address-label formatter for Stage 5 web layer"
```

---

## Task 2: `join_address_labels` and `join_occupancy_context`

**Files:**
- Modify: `src/web_layer.py`
- Test: `tests/test_web_layer.py`

**Interfaces:**
- Consumes: `build_address_label` from Task 1.
- Produces:
  - `join_address_labels(results_gdf: gpd.GeoDataFrame, portal_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame` — left-joins on `id_porpk`, adds an `address` column. `portal_gdf` must have `id_porpk`, `tvia`, `nombre`, `numero`.
  - `join_occupancy_context(results_gdf: gpd.GeoDataFrame, tagged_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame` — left-joins on `id_porpk`, adds `has_commercial_local`, `current_activity_summary` (parsed via `json.loads` from its GPKG string form into a real list-of-dicts), and `is_existing_hosteleria_class`. `tagged_gdf` must have `id_porpk`, `has_commercial_local`, `current_activity_summary`, `is_existing_hosteleria_class`.

- [ ] **Step 1: Write the failing test**

```python
import geopandas as gpd
from shapely.geometry import Point

from web_layer import join_address_labels, join_occupancy_context


def _results_gdf(id_porpks):
    return gpd.GeoDataFrame(
        {"id_porpk": id_porpks},
        geometry=[Point(0, 0) for _ in id_porpks],
        crs="EPSG:25830",
    )


def test_join_address_labels_attaches_label():
    results = _results_gdf([1, 2])
    portal = gpd.GeoDataFrame(
        {
            "id_porpk": [1, 2],
            "tvia": ["CALLE", "PLAZA"],
            "nombre": ["ARGANZUELA", "COLON"],
            "numero": ["2", "Desconocido"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:25830",
    )
    joined = join_address_labels(results, portal)
    labels = dict(zip(joined["id_porpk"], joined["address"]))
    assert labels[1] == "Calle Arganzuela, 2"
    assert labels[2] == "Plaza Colon"


def test_join_address_labels_left_join_keeps_unmatched_rows():
    results = _results_gdf([1, 99])  # 99 has no match in portal
    portal = gpd.GeoDataFrame(
        {"id_porpk": [1], "tvia": ["CALLE"], "nombre": ["ARGANZUELA"], "numero": ["2"]},
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_address_labels(results, portal)
    assert len(joined) == 2
    labels = dict(zip(joined["id_porpk"], joined["address"]))
    assert labels[1] == "Calle Arganzuela, 2"
    assert labels[99] is None


def test_join_occupancy_context_attaches_fields_and_parses_json():
    results = _results_gdf([1])
    tagged = gpd.GeoDataFrame(
        {
            "id_porpk": [1],
            "has_commercial_local": [True],
            "current_activity_summary": ['[{"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}]'],
            "is_existing_hosteleria_class": [True],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:25830",
    )
    joined = join_occupancy_context(results, tagged)
    row = joined.iloc[0]
    assert row["has_commercial_local"] is True
    assert row["is_existing_hosteleria_class"] is True
    assert row["current_activity_summary"] == [
        {"id_seccion": "I", "desc_epigrafe": "BAR RESTAURANTE", "desc_situacion_local": "Abierto"}
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_layer.py -v -k "join_address_labels or join_occupancy_context"`
Expected: FAIL with `ImportError: cannot import name 'join_address_labels'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/web_layer.py`:

```python
def join_address_labels(
    results_gdf: gpd.GeoDataFrame, portal_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Left-join results_gdf to portal_gdf on id_porpk, adding an
    'address' column. Rows with no match keep their other columns with a
    null address rather than being dropped."""
    labels = portal_gdf[["id_porpk", "tvia", "nombre", "numero"]].copy()
    labels["address"] = labels.apply(
        lambda row: build_address_label(row["tvia"], row["nombre"], row["numero"]), axis=1,
    )
    return results_gdf.merge(labels[["id_porpk", "address"]], on="id_porpk", how="left")


def join_occupancy_context(
    results_gdf: gpd.GeoDataFrame, tagged_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Left-join results_gdf to tagged_gdf on id_porpk, adding
    has_commercial_local, current_activity_summary (parsed from its GPKG
    JSON-string form into a real list-of-dicts), and
    is_existing_hosteleria_class."""
    context = tagged_gdf[[
        "id_porpk", "has_commercial_local", "current_activity_summary",
        "is_existing_hosteleria_class",
    ]].copy()
    context["current_activity_summary"] = context["current_activity_summary"].apply(
        lambda value: json.loads(value) if isinstance(value, str) else value
    )
    return results_gdf.merge(context, on="id_porpk", how="left")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_layer.py -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
git add src/web_layer.py tests/test_web_layer.py
git commit -m "Add address and occupancy-context join helpers for Stage 5 web layer"
```

---

## Task 3: `reproject_competitor_locations`

**Files:**
- Modify: `src/web_layer.py`
- Test: `tests/test_web_layer.py`

**Interfaces:**
- Produces: `reproject_competitor_locations(gdf: gpd.GeoDataFrame, x_col: str, y_col: str, source_crs: str) -> tuple[list, list]` — returns `(lons, lats)`, same length/order as `gdf`, with `None` passed through for rows where `gdf[x_col]` or `gdf[y_col]` is `None`/NaN.

- [ ] **Step 1: Write the failing test**

```python
import math

from web_layer import reproject_competitor_locations


def test_reproject_competitor_locations_known_coordinate():
    # A known EPSG:25830 point in central Madrid; expected lon/lat computed
    # independently via pyproj.Transformer (verified against
    # EPSG:25830 -> EPSG:4326 for this exact input).
    gdf = _results_gdf([1])
    gdf["comp_x"] = [440000.0]
    gdf["comp_y"] = [4474000.0]
    lons, lats = reproject_competitor_locations(gdf, "comp_x", "comp_y", "EPSG:25830")
    assert math.isclose(lons[0], -3.7071991233876656, abs_tol=1e-4)
    assert math.isclose(lats[0], 40.41446049371108, abs_tol=1e-4)


def test_reproject_competitor_locations_passes_through_none():
    gdf = _results_gdf([1, 2])
    gdf["comp_x"] = [440000.0, None]
    gdf["comp_y"] = [4474000.0, None]
    lons, lats = reproject_competitor_locations(gdf, "comp_x", "comp_y", "EPSG:25830")
    assert lons[1] is None
    assert lats[1] is None
    assert lons[0] is not None
```

(Uses the `_results_gdf` helper already defined earlier in the file from Task 2 — don't redefine it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_layer.py -v -k reproject_competitor_locations`
Expected: FAIL with `ImportError: cannot import name 'reproject_competitor_locations'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/web_layer.py`:

```python
def reproject_competitor_locations(
    gdf: gpd.GeoDataFrame, x_col: str, y_col: str, source_crs: str
) -> tuple[list, list]:
    """Reproject a competitor-location x/y column pair (plain floats, not
    GeoDataFrame geometry -- e.g. the nearest-competitor lookup columns
    from Stage 4) from source_crs to EPSG:4326. Returns (lons, lats),
    same order as gdf. None/NaN input coordinates pass through as None
    rather than being reprojected."""
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    lons, lats = [], []
    for x, y in zip(gdf[x_col], gdf[y_col]):
        if x is None or y is None or (isinstance(x, float) and math.isnan(x)):
            lons.append(None)
            lats.append(None)
            continue
        lon, lat = transformer.transform(x, y)
        lons.append(lon)
        lats.append(lat)
    return lons, lats
```

Add `import math` to the top of `src/web_layer.py` alongside the existing `import json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_layer.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/web_layer.py tests/test_web_layer.py
git commit -m "Add competitor-location reprojection helper for Stage 5 web layer"
```

---

## Task 4: `scripts/09_build_web_layer.py`

**Files:**
- Create: `scripts/09_build_web_layer.py`

**Interfaces:**
- Consumes: `join_address_labels`, `join_occupancy_context`, `reproject_competitor_locations` from `src/web_layer.py` (Tasks 1-3).
- Produces: `data/processed/zpae_viability_map.geojson`.

This task has no isolated unit test of its own (it's an orchestration
script) — Tasks 1-3 already cover `web_layer.py`'s correctness in
isolation. Verification is a syntax check plus, if the real processed data
files happen to be present in this environment, a real end-to-end smoke
run.

- [ ] **Step 1: Write the script**

```python
"""
Stage 5: assemble the single static file the eventual map website loads --
Stage 4's pass/fail + competitor-identity results, joined with a
human-readable address label and today's occupancy context, reprojected
to EPSG:4326. See
docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md.

Run locally (after scripts/08_compute_distances.py has produced its
output -- re-run it first if it predates the nearest-competitor-identity
columns):
    python scripts/09_build_web_layer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from web_layer import join_address_labels, join_occupancy_context, reproject_competitor_locations

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
SOURCE_CRS = "EPSG:25830"
COMPETITOR_LOOKUP_PREFIXES = [
    "strict_nearest_binding", "lenient_nearest_binding",
    "strict_nearest_overall", "lenient_nearest_overall",
]

results = gpd.read_file(PROCESSED_DIR / "distance_evaluation_results.gpkg")
print(f"Loaded {len(results)} evaluated candidates.")

missing_columns = [
    f"{prefix}_id_local" for prefix in COMPETITOR_LOOKUP_PREFIXES
    if f"{prefix}_id_local" not in results.columns
]
if missing_columns:
    raise RuntimeError(
        f"distance_evaluation_results.gpkg is missing competitor-identity "
        f"columns {missing_columns} -- re-run scripts/08_compute_distances.py "
        f"to regenerate it before building the web layer."
    )

portal = gpd.read_file(PROCESSED_DIR / "rt_portalpk_p_zpae_clip.gpkg")
tagged = gpd.read_file(PROCESSED_DIR / "candidate_addresses_zpae_tagged.gpkg")

results = join_address_labels(results, portal)
results = join_occupancy_context(results, tagged)
print(f"After joins: {len(results)} rows, {len(results.columns)} columns.")

for prefix in COMPETITOR_LOOKUP_PREFIXES:
    lons, lats = reproject_competitor_locations(results, f"{prefix}_x", f"{prefix}_y", SOURCE_CRS)
    results[f"{prefix}_lon"] = lons
    results[f"{prefix}_lat"] = lats

results = results.to_crs("EPSG:4326")

out_path = PROCESSED_DIR / "zpae_viability_map.geojson"
results.to_file(out_path, driver="GeoJSON")
print(f"Saved to {out_path}")
```

- [ ] **Step 2: Syntax check**

Run: `python -c "import ast; ast.parse(open('scripts/09_build_web_layer.py').read())"`
Expected: no output (valid syntax)

- [ ] **Step 3: Real-data smoke check, if the data is present**

Check first: `ls data/processed/distance_evaluation_results.gpkg
data/processed/rt_portalpk_p_zpae_clip.gpkg
data/processed/candidate_addresses_zpae_tagged.gpkg 2>&1`.

If all three exist, first confirm `distance_evaluation_results.gpkg` has
the competitor-identity columns (re-run `python scripts/08_compute_distances.py`
first if not — check with
`python3 -c "import geopandas as gpd; print('strict_nearest_binding_id_local' in gpd.read_file('data/processed/distance_evaluation_results.gpkg', rows=1).columns)"`,
expect `True`), then run:

```bash
python scripts/09_build_web_layer.py
```

Expected: prints row/column counts and `Saved to ...zpae_viability_map.geojson`,
no traceback. Then verify the output:

```bash
python3 -c "
import geopandas as gpd
gdf = gpd.read_file('data/processed/zpae_viability_map.geojson')
print(len(gdf), 'rows')
print(gdf.crs)
print(gdf[['address', 'has_commercial_local', 'current_activity_summary']].head(3))
row = gdf.iloc[0]
print(type(row['current_activity_summary']))
"
```

Expected: 9,838 rows, CRS is EPSG:4326, `address` values look like
`"Calle Arganzuela, 2"`, and `current_activity_summary` on a row that has
one is a real Python `list` (not a string) after GeoJSON round-trip.

If the three input files are NOT present (e.g. a fresh worktree branched
from `origin/main`, which doesn't carry gitignored data files), skip this
step — the syntax check in Step 2 and Tasks 1-3's unit tests are the
available verification in that environment. Note this explicitly in the
report rather than silently skipping.

- [ ] **Step 4: Commit**

```bash
git add scripts/09_build_web_layer.py
git commit -m "Add Stage 5 script to build the static web layer"
```

(Do not commit `data/processed/zpae_viability_map.geojson` itself if Step 3
produced one — check `.gitignore` covers `data/processed/`, matching every
prior stage's output, before running `git add`.)

---

## Task 5: Update docs

**Files:**
- Modify: `docs/data_sources.md`
- Modify: `README.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Add a note to `docs/data_sources.md`**

Add a short section documenting `zpae_viability_map.geojson`: its inputs
(the three joined files), its scope (9,838 evaluable candidates, EPSG:4326),
the new fields it adds (`address`, `has_commercial_local`,
`current_activity_summary` as real nested JSON, `is_existing_hosteleria_class`,
and the `_lon`/`_lat` companions for each of the 4 competitor lookups), and
the prerequisite that `scripts/08_compute_distances.py` must be re-run
first if stale. Cross-reference
`docs/superpowers/specs/2026-07-20-stage5-web-layer-design.md`.

- [ ] **Step 2: Update `README.md`'s Status section**

Change "Stage 5 — not started" (or the current "Stages 5-6 — not started
yet" bullet) to mark Stage 5 done, with one or two sentences describing
what it produces (the static `zpae_viability_map.geojson`, ready for a map
website to load directly) and that Stage 6 (the website itself) remains.

- [ ] **Step 3: Commit**

```bash
git add docs/data_sources.md README.md
git commit -m "Document Stage 5 web layer in README and data_sources.md"
```

---

## Self-Review Notes

- **Spec coverage:** address-label formatting (including both confirmed
  real-data edge cases: `"Desconocido"` numero and null tvia), both join
  helpers (including left-join-keeps-unmatched and JSON-string parsing),
  competitor-location reprojection (including None pass-through), the
  orchestration script (including the fail-loud prerequisite check), and
  doc updates are all covered by Tasks 1-5, matching the design doc's
  Architecture and Testing sections.
- **Placeholder scan:** none found — every step has runnable code or an
  exact command with expected output.
- **Type consistency:** `join_address_labels`/`join_occupancy_context`/
  `reproject_competitor_locations` signatures match across their
  definitions (Tasks 2-3) and their use in `scripts/09_build_web_layer.py`
  (Task 4) — same parameter names, same return shapes.
