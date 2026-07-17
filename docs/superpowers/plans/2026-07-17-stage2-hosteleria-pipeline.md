# Stage 2 Hostelería Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the hostelería competitor point layer and candidate-address commercial-local context for the four ZPAE zones, from datos.madrid.es's CKAN datastore API.

**Architecture:** Two new pure-logic modules (`src/activities.py` for the epígrafe→Decreto-184/1998 mapping, `src/hosteleria.py` for filtering/classifying/joining) consumed by two orchestration scripts (`scripts/03_fetch_hosteleria.py`, `scripts/04_reconcile_hosteleria.py`), mirroring Stage 1's fetch→reconcile split. A shared `src/zpae_geometry.py` extracts the study-area buffer logic already in `scripts/02_clip_network_to_zpae.py` so it isn't duplicated.

**Tech Stack:** Python, geopandas, shapely, requests, pytest. Same minimal venv as Stage 1 (`requirements.txt`).

## Global Constraints

- Native CRS is EPSG:25830 (ETRS89 / UTM 30N) everywhere — matches Stage 1's convention (see `docs/data_sources.md`).
- Every module importable by bare name from `src/` via `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))` at the top of scripts/tests — this repo has no package/`__init__.py` setup, and Stage 1 already established this ad hoc pattern; don't introduce a different import mechanism.
- Any paginated API fetch MUST assert the fetched row count against the API's reported total before treating the fetch as complete — the ArcGIS `exceededTransferLimit` bug from Stage 1 (silently returning 2000 of 2590 rows) is exactly the failure mode the CKAN datastore API can also hit.
- Unmapped epígrafe codes must be surfaced loudly (printed warnings, not silently dropped) — same "flag data quality issues rather than silently working around them" standard Stage 1 followed.
- `data/` and `.venv/` stay gitignored (already configured) — no raw/processed data files get committed.

---

## File Structure

- `src/zpae_geometry.py` (new) — `build_study_area()`, extracted from `scripts/02_clip_network_to_zpae.py`.
- `src/activities.py` (new) — epígrafe → Decreto 184/1998 mapping + `classify_epigrafe()`.
- `src/ckan.py` (new) — CKAN datastore API helpers: `fetch_all_records()`, `assert_pagination_complete()`, `build_point_geometry()`.
- `src/hosteleria.py` (new) — `build_competitor_layer()`, `join_candidate_context()`, `summarize_candidate_context()`.
- `scripts/02_clip_network_to_zpae.py` (modify) — use `zpae_geometry.build_study_area()` instead of inline dissolve/buffer.
- `scripts/03_fetch_hosteleria.py` (new) — fetch orchestration.
- `scripts/04_reconcile_hosteleria.py` (new) — reconcile orchestration, both outputs A and B.
- `tests/conftest.py` (new) — sys.path setup so tests can `import activities`, etc.
- `tests/test_zpae_geometry.py`, `tests/test_activities.py`, `tests/test_ckan.py`, `tests/test_hosteleria.py` (new).
- `pytest.ini` (new) — `testpaths = tests`.
- `requirements.txt` (modify) — add `pytest`, `requests`, `shapely`.
- `docs/data_sources.md` (modify) — document the confirmed CKAN API details.

---

### Task 1: Extract shared study-area buffer logic + pytest setup

**Files:**
- Create: `src/zpae_geometry.py`
- Create: `tests/conftest.py`
- Create: `tests/test_zpae_geometry.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`
- Modify: `scripts/02_clip_network_to_zpae.py`

**Interfaces:**
- Produces: `zpae_geometry.build_study_area(zpae_ambitos: geopandas.GeoDataFrame, buffer_m: float) -> shapely.geometry.base.BaseGeometry` — used by Task 7's `scripts/04_reconcile_hosteleria.py`.

- [ ] **Step 1: Add test/runtime dependencies**

Edit `requirements.txt` to:

```
geopandas
fiona
pyogrio
shapely
requests
pytest
```

- [ ] **Step 2: Install and verify**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: successful install, no errors (pytest/requests/shapely are new; geopandas/fiona/pyogrio already satisfied).

- [ ] **Step 3: Create pytest config and path setup**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
```

Create `tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
```

- [ ] **Step 4: Write the failing test for `build_study_area`**

Create `tests/test_zpae_geometry.py`:

```python
import geopandas as gpd
from shapely.geometry import Polygon

from zpae_geometry import build_study_area


def test_build_study_area_buffers_and_dissolves():
    square1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    square2 = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    gdf = gpd.GeoDataFrame(
        {"ZPAE": ["a", "b"]}, geometry=[square1, square2], crs="EPSG:25830"
    )

    result = build_study_area(gdf, buffer_m=5)

    minx, miny, maxx, maxy = result.bounds
    assert minx == -5
    assert miny == -5
    assert maxx == 35
    assert maxy == 15


def test_build_study_area_reprojects_when_crs_differs():
    # a 1x1 degree box roughly over Madrid in EPSG:4326 -- just needs to
    # not raise and to produce a geometry in metres-scale coordinates
    # after reprojection to EPSG:25830.
    square = Polygon([(-3.71, 40.41), (-3.70, 40.41), (-3.70, 40.42), (-3.71, 40.42)])
    gdf = gpd.GeoDataFrame({"ZPAE": ["a"]}, geometry=[square], crs="EPSG:4326")

    result = build_study_area(gdf, buffer_m=10)

    minx, miny, maxx, maxy = result.bounds
    assert minx > 100000  # EPSG:25830 easting for Madrid is in the ~400000s
    assert maxx < 900000
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_zpae_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zpae_geometry'`

- [ ] **Step 6: Implement `build_study_area`**

Create `src/zpae_geometry.py`:

```python
"""
Shared ZPAE study-area geometry helper, used by both the network clip
(scripts/02_clip_network_to_zpae.py) and the hostelería reconcile
pipeline (scripts/04_reconcile_hosteleria.py) so the dissolve+buffer
logic lives in one place instead of being copy-pasted.
"""

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

TARGET_CRS = "EPSG:25830"  # ETRS89 / UTM 30N, metres


def build_study_area(zpae_ambitos: gpd.GeoDataFrame, buffer_m: float) -> BaseGeometry:
    """Dissolve the ZPAE zone boundary polygons into one buffered study-area
    geometry, reprojecting to TARGET_CRS first if the input isn't already
    in it."""
    if zpae_ambitos.crs is None:
        zpae_ambitos = zpae_ambitos.set_crs(TARGET_CRS)
    else:
        zpae_ambitos = zpae_ambitos.to_crs(TARGET_CRS)
    return zpae_ambitos.dissolve().buffer(buffer_m).iloc[0]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_zpae_geometry.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Refactor script 02 to use the shared helper**

Edit `scripts/02_clip_network_to_zpae.py` — replace the CRS/dissolve/buffer block with a call to the new helper. Full updated file:

```python
"""
Stage 1/2: clip the (Comunidad de Madrid-wide) IGR-RT geopackage down to
just the four ZPAE zones plus a buffer, so downstream steps don't have to
carry the whole regional network around.

Buffer size: set generously above the largest plausible threshold you find
in Stage 1's ZPAE Normativa dump (secondary sources suggested up to 150m --
use 250-300m to be safe, since network distance along streets is always
>= straight-line distance, so a small straight-line buffer can still clip
off a legitimate route).

Uses zpae_ambitos.geojson (the 4 zone boundary polygons, one per zone) for
the dissolve+buffer study area -- not zpae_clasificacion.geojson, which is
a line layer (per-street classification) and isn't suitable for that.

Run locally:
    python scripts/02_clip_network_to_zpae.py \
        --igrrt-gpkg /path/to/your/downloaded/red_viaria.gpkg \
        --zpae-geojson data/raw/zpae/zpae_ambitos.geojson \
        --buffer-m 300
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from zpae_geometry import TARGET_CRS, build_study_area


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--igrrt-gpkg", required=True, type=Path)
    ap.add_argument(
        "--zpae-geojson",
        default=Path("data/raw/zpae/zpae_ambitos.geojson"),
        type=Path,
    )
    ap.add_argument("--buffer-m", default=300, type=float)
    ap.add_argument(
        "--out-dir", default=Path("data/processed"), type=Path
    )
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    zpae = gpd.read_file(args.zpae_geojson)
    study_area = build_study_area(zpae, args.buffer_m)

    # list layers in the geopackage first so you can confirm exact names
    # match what QGIS showed you (rt_tramo_vial, rt_portalpk_p)
    import fiona

    layers = fiona.listlayers(args.igrrt_gpkg)
    print(f"Layers found in {args.igrrt_gpkg.name}: {layers}")

    for layer_name in ("rt_tramo_vial", "rt_portalpk_p"):
        if layer_name not in layers:
            print(f"  [!] '{layer_name}' not found -- check exact layer "
                  f"name above and adjust the script.")
            continue

        gdf = gpd.read_file(args.igrrt_gpkg, layer=layer_name)
        if gdf.crs is None:
            print(f"  [!] {layer_name} has no CRS set -- confirm manually "
                  f"before trusting this clip (assuming {TARGET_CRS}).")
            gdf = gdf.set_crs(TARGET_CRS)
        else:
            gdf = gdf.to_crs(TARGET_CRS)

        before = len(gdf)
        clipped = gdf[gdf.intersects(study_area)]
        after = len(clipped)
        print(f"  {layer_name}: {before} -> {after} features after clip")

        out_path = args.out_dir / f"{layer_name}_zpae_clip.gpkg"
        clipped.to_file(out_path, driver="GPKG")
        print(f"  Saved to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Regression-check script 02 still produces identical output**

Run: `source .venv/bin/activate && python scripts/02_clip_network_to_zpae.py --igrrt-gpkg data/RT_MADRID_gpkg/red_viaria.gpkg --buffer-m 300`
Expected: same counts as Stage 1's original run — `rt_tramo_vial: 313402 -> 4380`, `rt_portalpk_p: 743624 -> 13876`. If the counts differ, the refactor changed behavior — stop and fix before proceeding.

- [ ] **Step 10: Commit**

```bash
git add requirements.txt pytest.ini tests/conftest.py tests/test_zpae_geometry.py src/zpae_geometry.py scripts/02_clip_network_to_zpae.py
git commit -m "$(cat <<'EOF'
Extract shared study-area buffer helper, add pytest setup

src/zpae_geometry.py holds the dissolve+buffer logic previously inline
in scripts/02_clip_network_to_zpae.py, so Stage 2's reconcile script
can reuse it without duplicating. Also adds pytest/requests/shapely as
explicit dependencies and the tests/ scaffolding Stage 2 needs.
EOF
)"
```

---

### Task 2: Epígrafe → Decreto 184/1998 activity classification

**Files:**
- Create: `src/activities.py`
- Create: `tests/test_activities.py`

**Interfaces:**
- Consumes: nothing (pure module, no dependencies on other new code).
- Produces: `activities.classify_epigrafe(id_seccion: str, id_epigrafe: str) -> activities.EpigrafeClassification` (dataclass with `status: str` — one of `"mapped"`, `"excluded"`, `"unmapped"`, `"not_applicable"` — and `decreto_class: str | None`) — used by Task 4's `scripts/03_fetch_hosteleria.py` and Task 5's `src/hosteleria.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_activities.py`:

```python
from activities import EpigrafeClassification, classify_epigrafe


def test_mapped_hosteleria_epigrafe():
    result = classify_epigrafe("I", "561001")  # RESTAURANTE
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_v_cat10")


def test_mapped_discoteca_epigrafe():
    result = classify_epigrafe("R", "932006")  # DISCOTECAS Y SALAS DE BAILE
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_iv_cat4")


def test_mapped_bar_especial_epigrafe():
    result = classify_epigrafe("I", "563003")  # BAR ESPECIAL CON ACTUACIONES
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_v_cat9")


def test_mapped_cafe_espectaculo_epigrafe():
    result = classify_epigrafe("I", "563007")  # CAFE ESPECTACULO
    assert result == EpigrafeClassification(status="mapped", decreto_class="clase_iii_cat1")


def test_excluded_epigrafe():
    result = classify_epigrafe("I", "563006")  # CIBER-CAFE
    assert result == EpigrafeClassification(status="excluded")


def test_excluded_institutional_catering_epigrafe():
    result = classify_epigrafe("I", "562902")  # SERVICIOS DE COMEDOR EN CENTROS EDUCATIVOS
    assert result == EpigrafeClassification(status="excluded")


def test_unmapped_epigrafe_in_relevant_seccion():
    # simulates a real gap: a seccion I/R code not in our mapping table
    result = classify_epigrafe("I", "999999")
    assert result == EpigrafeClassification(status="unmapped")


def test_not_applicable_outside_seccion_i_r():
    result = classify_epigrafe("G", "471101")  # retail, unrelated seccion
    assert result == EpigrafeClassification(status="not_applicable")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_activities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'activities'`

- [ ] **Step 3: Implement the mapping and classifier**

Create `src/activities.py`:

```python
"""
Maps censo de locales activity epígrafes (CNAE-based, from CKAN resource
200085-5-censo-locales on datos.madrid.es) to the Decreto 184/1998
class/categoría scheme used by every ZPAE zone's Normativa (see
src/zones.py and docs/data_sources.md for how the two relate).

Only seccion I (Hostelería) and R (Actividades artísticas, recreativas y
de entretenimiento) contain ZPAE-relevant epígrafes -- everything else is
"not_applicable". Confirmed against the live API 2026-07-17; see
docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md
for the full mapping table and the two documented gaps (Clase III Cat.2
"salas de conciertos", and hotel bars/restaurants with direct street
access) that are deliberately left unmapped rather than guessed.
"""

from dataclasses import dataclass

RELEVANT_SECCIONES = {"I", "R"}

EPIGRAFE_TO_DECRETO_CLASS = {
    # Clase III Cat.1 -- esparcimiento y diversión
    "563007": "clase_iii_cat1",  # CAFE ESPECTACULO
    "932004": "clase_iii_cat1",  # SALAS DE FIESTA CON RESTAURACION
    "932005": "clase_iii_cat1",  # SALAS DE FIESTA SIN RESTAURACION
    # Clase IV Cat.4 -- de baile
    "932006": "clase_iv_cat4",   # DISCOTECAS Y SALAS DE BAILE
    # Clase V Cat.9 -- ocio y diversión
    "563002": "clase_v_cat9",    # BAR ESPECIAL SIN ACTUACIONES
    "563003": "clase_v_cat9",    # BAR ESPECIAL CON ACTUACIONES
    # Clase V Cat.10 -- hostelería y restauración
    "561001": "clase_v_cat10",   # RESTAURANTE
    "561002": "clase_v_cat10",   # RESTAURANTES DE COMIDA RAPIDA
    "561003": "clase_v_cat10",   # AUTOSERVICIO DE RESTAURACION
    "561004": "clase_v_cat10",   # BAR RESTAURANTE
    "561005": "clase_v_cat10",   # BAR CON COCINA
    "561006": "clase_v_cat10",   # CAFETERIA
    "561007": "clase_v_cat10",   # CHOCOLATERIA/SALON DE TE Y HELADERIA
    "563001": "clase_v_cat10",   # BODEGA CON CONSUMO
    "563004": "clase_v_cat10",   # TABERNA
    "563005": "clase_v_cat10",   # BAR SIN COCINA
    "562101": "clase_v_cat10",   # SALONES DE BANQUETES
}

# Present in seccion I/R but deliberately NOT gated by the ZPAE
# hostelería/ocio rules -- see design doc for the reasoning behind each.
EXCLUDED_EPIGRAFES = {
    "561008",  # VENDEDOR AMBULANTE / RESTAURACION MOVIL -- no fixed premises
    "562901",  # COMIDAS EN INSTALACIONES DEPORTIVAS, OFICINAS -- not open to the public
    "562902",  # COMEDOR EN CENTROS EDUCATIVOS/CUIDADO INFANTIL -- not open to the public
    "562903",  # COMEDOR EN CENTROS PARA MAYORES -- not open to the public
    "562904",  # COMEDOR EN CENTROS DE SERVICIOS SOCIALES -- not open to the public
    "562905",  # PREPARACION DE COMIDAS EN HOSPITALES -- not open to the public
    "563006",  # CIBER-CAFE
}


@dataclass(frozen=True)
class EpigrafeClassification:
    status: str  # "mapped" | "excluded" | "unmapped" | "not_applicable"
    decreto_class: str | None = None


def classify_epigrafe(id_seccion: str, id_epigrafe: str) -> EpigrafeClassification:
    """Classify a censo de locales epígrafe against the Decreto 184/1998
    scheme. Only seccion I/R are ZPAE-relevant; anything else is
    "not_applicable" without consulting the mapping tables."""
    if id_seccion not in RELEVANT_SECCIONES:
        return EpigrafeClassification(status="not_applicable")
    if id_epigrafe in EXCLUDED_EPIGRAFES:
        return EpigrafeClassification(status="excluded")
    if id_epigrafe in EPIGRAFE_TO_DECRETO_CLASS:
        return EpigrafeClassification(
            status="mapped",
            decreto_class=EPIGRAFE_TO_DECRETO_CLASS[id_epigrafe],
        )
    return EpigrafeClassification(status="unmapped")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_activities.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/activities.py tests/test_activities.py
git commit -m "$(cat <<'EOF'
Add epígrafe to Decreto 184/1998 activity classification

Maps censo de locales' CNAE-based id_epigrafe codes to the class/
categoría scheme used in every ZPAE zone's Normativa. Confident
mappings for Clase III Cat.1, Clase IV Cat.4, Clase V Cat.9/10;
Clase III Cat.2 (salas de conciertos) has no matching epígrafe and is
left as a documented gap rather than guessed.
EOF
)"
```

---

### Task 3: CKAN datastore API helpers

**Files:**
- Create: `src/ckan.py`
- Create: `tests/test_ckan.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ckan.fetch_all_records(resource_id: str, where_sql: str, page_size: int = 1000, http_post: Callable = requests.post) -> list[dict]`, `ckan.assert_pagination_complete(fetched_count: int, reported_total: int) -> None` (raises `ValueError`), `ckan.build_point_geometry(x: str, y: str) -> shapely.geometry.Point` — used by Task 4's `scripts/03_fetch_hosteleria.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ckan.py`:

```python
import pytest

from ckan import assert_pagination_complete, build_point_geometry, fetch_all_records


def test_assert_pagination_complete_passes_when_equal():
    assert_pagination_complete(100, 100)  # no exception


def test_assert_pagination_complete_raises_when_mismatched():
    with pytest.raises(ValueError):
        assert_pagination_complete(50, 100)


def test_build_point_geometry():
    point = build_point_geometry("440554.59", "4475338.53")
    assert point.x == 440554.59
    assert point.y == 4475338.53


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_http_post_factory(pages, total):
    """Serves `pages` (a list of record-lists) in sequence for successive
    LIMIT/OFFSET calls, and answers COUNT(*) queries with `total`."""
    calls = {"n": 0}

    def fake_post(url, data, timeout):
        sql = data["sql"]
        if sql.startswith("SELECT COUNT(*)"):
            return _FakeResponse({"result": {"records": [{"count": total}]}})
        idx = calls["n"]
        calls["n"] += 1
        page = pages[idx] if idx < len(pages) else []
        return _FakeResponse({"result": {"records": page}})

    return fake_post


def test_fetch_all_records_paginates_until_total_reached():
    pages = [
        [{"id": 1}, {"id": 2}],
        [{"id": 3}],
    ]
    fake_post = _fake_http_post_factory(pages, total=3)

    records = fetch_all_records(
        "some-resource", "1=1", page_size=2, http_post=fake_post
    )

    assert records == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_fetch_all_records_raises_if_total_not_reached():
    pages = [[{"id": 1}, {"id": 2}]]
    fake_post = _fake_http_post_factory(pages, total=5)

    with pytest.raises(ValueError):
        fetch_all_records("some-resource", "1=1", page_size=2, http_post=fake_post)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_ckan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ckan'`

- [ ] **Step 3: Implement the CKAN helpers**

Create `src/ckan.py`:

```python
"""
Shared helpers for querying datos.madrid.es's CKAN datastore API
(https://datos.madrid.es/api/3/action/datastore_search_sql). The API
caps rows per request and doesn't error on truncation -- the same
failure mode as the ArcGIS `exceededTransferLimit` bug found in Stage 1
(scripts/01_fetch_zpae.py) -- so callers MUST rely on
assert_pagination_complete rather than trusting a short final page to
mean "done".
"""

from typing import Callable

import requests
from shapely.geometry import Point

SQL_ENDPOINT = "https://datos.madrid.es/api/3/action/datastore_search_sql"


def assert_pagination_complete(fetched_count: int, reported_total: int) -> None:
    """Raise if a paginated fetch stopped short of the API's reported
    total row count."""
    if fetched_count != reported_total:
        raise ValueError(
            f"Pagination incomplete: fetched {fetched_count} rows but "
            f"the API reports {reported_total} total -- a page was "
            f"dropped or the loop stopped early."
        )


def build_point_geometry(x: str, y: str) -> Point:
    """Build a shapely Point from the censo de locales'
    coordenada_x_local/coordenada_y_local string fields."""
    return Point(float(x), float(y))


def fetch_all_records(
    resource_id: str,
    where_sql: str,
    page_size: int = 1000,
    http_post: Callable[..., "requests.Response"] = requests.post,
) -> list[dict]:
    """Fetch every row matching where_sql from a CKAN datastore resource,
    paginating with LIMIT/OFFSET until the fetched count matches the
    API's reported total. `http_post` is injectable for testing."""
    records: list[dict] = []
    offset = 0
    total = None
    while True:
        sql = (
            f'SELECT * FROM "{resource_id}" WHERE {where_sql} '
            f"LIMIT {page_size} OFFSET {offset}"
        )
        resp = http_post(SQL_ENDPOINT, data={"sql": sql}, timeout=60)
        resp.raise_for_status()
        page = resp.json()["result"]["records"]
        records.extend(page)

        if total is None:
            count_sql = f'SELECT COUNT(*) FROM "{resource_id}" WHERE {where_sql}'
            count_resp = http_post(SQL_ENDPOINT, data={"sql": count_sql}, timeout=60)
            count_resp.raise_for_status()
            total = int(count_resp.json()["result"]["records"][0]["count"])

        if not page or len(records) >= total:
            break
        offset += page_size

    assert_pagination_complete(len(records), total)
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_ckan.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ckan.py tests/test_ckan.py
git commit -m "$(cat <<'EOF'
Add CKAN datastore API helpers with pagination-completeness guard

fetch_all_records paginates via LIMIT/OFFSET and asserts the fetched
count against the API's reported total -- the CKAN datastore API has
the same silent-truncation risk that bit the ArcGIS ZPAE fetch in
Stage 1, so this is asserted rather than assumed.
EOF
)"
```

---

### Task 4: Fetch script (raw citywide censo de locales pull)

**Files:**
- Create: `scripts/03_fetch_hosteleria.py`

**Interfaces:**
- Consumes: `activities.classify_epigrafe` (Task 2), `ckan.fetch_all_records`, `ckan.build_point_geometry` (Task 3).
- Produces: `data/raw/hosteleria/censo_locales_full.geojson` — consumed by Task 7's `scripts/04_reconcile_hosteleria.py`.

This task has no unit tests of its own (it's an I/O orchestration script over already-tested pure functions, same pattern as `scripts/01_fetch_zpae.py`) — verification is a live run against the real API.

- [ ] **Step 1: Write the fetch script**

Create `scripts/03_fetch_hosteleria.py`:

```python
"""
Stage 2: pull the full citywide censo de locales y actividades dataset
(all sections except "Uso vivienda") from datos.madrid.es's CKAN
datastore API, so both the hostelería/ocio competitor layer and the
candidate-address commercial context (scripts/04) can be derived from a
single fetch rather than querying the same resource twice.

Run locally:
    python scripts/03_fetch_hosteleria.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from activities import classify_epigrafe
from ckan import build_point_geometry, fetch_all_records

RESOURCE_ID = "200085-5-censo-locales"
# id_situacion_local '5' is "Uso vivienda" -- converted to residential,
# no longer a commercial premises. Everything else is kept: "Cerrado"
# is the vacant-but-commercial case this stage exists to capture.
WHERE_SQL = "id_situacion_local != '5'"

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "hosteleria"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Fetching {RESOURCE_ID} where {WHERE_SQL} ...")
records = fetch_all_records(RESOURCE_ID, WHERE_SQL)
print(f"Fetched {len(records)} records.")

unmapped = set()
for row in records:
    if row["id_seccion"] in ("I", "R"):
        result = classify_epigrafe(row["id_seccion"], row["id_epigrafe"])
        if result.status == "unmapped":
            unmapped.add((row["id_epigrafe"], row["desc_epigrafe"]))

if unmapped:
    print(f"\n[!] {len(unmapped)} seccion I/R epígrafe(s) have no mapping "
          f"in src/activities.py -- these rows will be dropped by "
          f"scripts/04_reconcile_hosteleria.py, not silently included:")
    for code, desc in sorted(unmapped):
        print(f"    {code}  {desc}")
else:
    print("\nAll seccion I/R epígrafes found are mapped or explicitly excluded.")

points = [
    build_point_geometry(r["coordenada_x_local"], r["coordenada_y_local"])
    for r in records
]
gdf = gpd.GeoDataFrame(records, geometry=points, crs="EPSG:25830")
print(f"\nBounds (EPSG:25830): {gdf.total_bounds}")

out_path = OUT_DIR / "censo_locales_full.geojson"
gdf.to_file(out_path, driver="GeoJSON")
print(f"Saved to {out_path}")
```

- [ ] **Step 2: Run it against the real API**

Run: `source .venv/bin/activate && python scripts/03_fetch_hosteleria.py`
Expected: `Fetched 216788 records.` (225,268 total minus 8,480 "Uso vivienda", per the counts confirmed during design). Bounds should fall within Madrid's EPSG:25830 extent (roughly x: 420000-450000, y: 4465000-4490000). Check the unmapped-epígrafe warning list: any code shown there needs a decision — either add it to `EPIGRAFE_TO_DECRETO_CLASS` or `EXCLUDED_EPIGRAFES` in `src/activities.py` and re-run, or accept it as a documented gap like Clase III Cat.2. Do not proceed to Task 7 with unexplained unmapped codes.

- [ ] **Step 3: Commit**

```bash
git add scripts/03_fetch_hosteleria.py
git commit -m "$(cat <<'EOF'
Add fetch script for citywide censo de locales pull

Pulls all sections except "Uso vivienda" in one request so both the
competitor layer and candidate-address context (scripts/04) can be
derived from a single fetch. Surfaces any seccion I/R epígrafe not
yet in src/activities.py's mapping instead of silently dropping it.
EOF
)"
```

---

### Task 5: Competitor layer builder

**Files:**
- Create: `src/hosteleria.py`
- Create: `tests/test_hosteleria.py`

**Interfaces:**
- Consumes: `activities.classify_epigrafe` (Task 2).
- Produces: `hosteleria.CompetitorBuildResult` (dataclass: `gdf: geopandas.GeoDataFrame`, `mapped_count: int`, `excluded_count: int`, `unmapped_count: int`, `unmapped_epigrafes: set[tuple[str, str]]`), `hosteleria.build_competitor_layer(records: list[dict]) -> CompetitorBuildResult` — used by Task 7's `scripts/04_reconcile_hosteleria.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hosteleria.py`:

```python
from hosteleria import build_competitor_layer


def _record(id_local, id_seccion, id_epigrafe, desc_epigrafe, desc_situacion_local,
            rotulo, x, y):
    return {
        "id_local": id_local,
        "id_seccion": id_seccion,
        "id_epigrafe": id_epigrafe,
        "desc_epigrafe": desc_epigrafe,
        "desc_situacion_local": desc_situacion_local,
        "rotulo": rotulo,
        "coordenada_x_local": x,
        "coordenada_y_local": y,
    }


def test_build_competitor_layer_filters_and_classifies():
    records = [
        _record("1", "I", "561001", "RESTAURANTE", "Abierto",
                "CASA PEPE", "440000.0", "4475000.0"),
        _record("2", "I", "563006", "CIBER-CAFE", "Abierto",
                "CIBER XYZ", "440100.0", "4475100.0"),
        _record("3", "I", "561001", "RESTAURANTE", "Cerrado",
                "CLOSED PLACE", "440200.0", "4475200.0"),
        _record("4", "R", "999999", "UNKNOWN ACTIVITY", "Abierto",
                "MYSTERY VENUE", "440300.0", "4475300.0"),
        _record("5", "G", "471101", "COMERCIO", "Abierto",
                "SHOP", "440400.0", "4475400.0"),
    ]

    result = build_competitor_layer(records)

    assert result.mapped_count == 1
    assert result.excluded_count == 1
    assert result.unmapped_count == 1
    assert result.unmapped_epigrafes == {("999999", "UNKNOWN ACTIVITY")}
    assert len(result.gdf) == 1
    assert result.gdf.iloc[0]["decreto_class"] == "clase_v_cat10"
    assert result.gdf.iloc[0]["id_local"] == "1"
    assert result.gdf.crs.to_string() == "EPSG:25830"


def test_build_competitor_layer_empty_input():
    result = build_competitor_layer([])
    assert result.mapped_count == 0
    assert len(result.gdf) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_hosteleria.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hosteleria'`

- [ ] **Step 3: Implement `build_competitor_layer`**

Create `src/hosteleria.py`:

```python
"""
Builds the two Stage 2 outputs from the raw censo de locales pull:
(A) the hostelería/ocio competitor point layer, and (B) commercial-local
context joined onto every candidate address point. See
docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md.
"""

from dataclasses import dataclass, field

import geopandas as gpd
from shapely.geometry import Point

from activities import classify_epigrafe

TARGET_CRS = "EPSG:25830"


@dataclass
class CompetitorBuildResult:
    gdf: gpd.GeoDataFrame
    mapped_count: int
    excluded_count: int
    unmapped_count: int
    unmapped_epigrafes: set = field(default_factory=set)


def build_competitor_layer(records: list[dict]) -> CompetitorBuildResult:
    """Filter raw censo de locales records to active seccion I/R rows,
    classify each against the Decreto 184/1998 scheme, and build the
    competitor point GeoDataFrame. Excluded/unmapped rows are dropped
    but counted, not silently discarded."""
    mapped_rows = []
    mapped_count = 0
    excluded_count = 0
    unmapped_count = 0
    unmapped_epigrafes = set()

    for row in records:
        if row["id_seccion"] not in ("I", "R"):
            continue
        if row["desc_situacion_local"] != "Abierto":
            continue

        result = classify_epigrafe(row["id_seccion"], row["id_epigrafe"])
        if result.status == "mapped":
            mapped_count += 1
            mapped_rows.append(
                {
                    "id_local": row["id_local"],
                    "rotulo": row["rotulo"],
                    "decreto_class": result.decreto_class,
                    "desc_epigrafe": row["desc_epigrafe"],
                    "geometry": Point(
                        float(row["coordenada_x_local"]),
                        float(row["coordenada_y_local"]),
                    ),
                }
            )
        elif result.status == "excluded":
            excluded_count += 1
        elif result.status == "unmapped":
            unmapped_count += 1
            unmapped_epigrafes.add((row["id_epigrafe"], row["desc_epigrafe"]))

    gdf = gpd.GeoDataFrame(mapped_rows, geometry="geometry", crs=TARGET_CRS)
    return CompetitorBuildResult(
        gdf=gdf,
        mapped_count=mapped_count,
        excluded_count=excluded_count,
        unmapped_count=unmapped_count,
        unmapped_epigrafes=unmapped_epigrafes,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_hosteleria.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hosteleria.py tests/test_hosteleria.py
git commit -m "$(cat <<'EOF'
Add build_competitor_layer: filter+classify censo records into the
hostelería/ocio competitor point layer

Keeps only active (Abierto) seccion I/R rows with a confident Decreto
184/1998 mapping; excluded and unmapped rows are dropped but counted
rather than silently discarded.
EOF
)"
```

---

### Task 6: Candidate address context join

**Files:**
- Modify: `src/hosteleria.py`
- Modify: `tests/test_hosteleria.py`

**Interfaces:**
- Consumes: `activities.classify_epigrafe` (Task 2).
- Produces: `hosteleria.join_candidate_context(addresses: geopandas.GeoDataFrame, locals_gdf: geopandas.GeoDataFrame, tolerance_m: float) -> geopandas.GeoDataFrame`, `hosteleria.summarize_candidate_context(joined: geopandas.GeoDataFrame, address_id_col: str) -> geopandas.GeoDataFrame` — used by Task 7's `scripts/04_reconcile_hosteleria.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hosteleria.py`:

```python
import geopandas as gpd
from shapely.geometry import Point

from hosteleria import join_candidate_context, summarize_candidate_context


def _locals_gdf():
    return gpd.GeoDataFrame(
        {
            "id_local": ["L1"],
            "id_seccion": ["I"],
            "id_epigrafe": ["561001"],
            "desc_epigrafe": ["RESTAURANTE"],
            "desc_situacion_local": ["Abierto"],
        },
        geometry=[Point(5, 5)],
        crs="EPSG:25830",
    )


def _addresses_gdf():
    return gpd.GeoDataFrame(
        {"id_porpk": ["a1", "a2"]},
        geometry=[Point(0, 0), Point(1000, 1000)],
        crs="EPSG:25830",
    )


def test_join_candidate_context_keeps_unmatched_addresses():
    joined = join_candidate_context(_addresses_gdf(), _locals_gdf(), tolerance_m=15)

    a1_rows = joined[joined["id_porpk"] == "a1"]
    a2_rows = joined[joined["id_porpk"] == "a2"]

    assert (a1_rows["id_local"] == "L1").all()
    assert a2_rows["id_local"].isna().all()


def test_summarize_candidate_context():
    joined = join_candidate_context(_addresses_gdf(), _locals_gdf(), tolerance_m=15)

    summary = summarize_candidate_context(joined, address_id_col="id_porpk")

    a1 = summary[summary["id_porpk"] == "a1"].iloc[0]
    a2 = summary[summary["id_porpk"] == "a2"].iloc[0]

    assert a1["has_commercial_local"] is True
    assert a1["is_existing_hosteleria_class"] is True
    assert a1["current_activity_summary"] == [
        {
            "id_seccion": "I",
            "desc_epigrafe": "RESTAURANTE",
            "desc_situacion_local": "Abierto",
        }
    ]

    assert a2["has_commercial_local"] is False
    assert a2["current_activity_summary"] == []
    assert a2["is_existing_hosteleria_class"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_hosteleria.py -v`
Expected: FAIL with `ImportError: cannot import name 'join_candidate_context'`

- [ ] **Step 3: Implement the join and summarize functions**

Append to `src/hosteleria.py`:

```python
def join_candidate_context(
    addresses: gpd.GeoDataFrame,
    locals_gdf: gpd.GeoDataFrame,
    tolerance_m: float,
) -> gpd.GeoDataFrame:
    """Nearest-join every candidate address point to the closest local(s)
    in locals_gdf within tolerance_m. Addresses with no local within
    tolerance keep all their own columns with null local-side fields
    (standard left-join semantics), rather than being dropped."""
    return gpd.sjoin_nearest(
        addresses,
        locals_gdf,
        how="left",
        max_distance=tolerance_m,
        distance_col="match_distance_m",
    )


def summarize_candidate_context(
    joined: gpd.GeoDataFrame, address_id_col: str
) -> gpd.GeoDataFrame:
    """Collapse the (possibly multiple-rows-per-address) nearest-join
    result down to one row per address, summarizing whether a commercial
    local exists nearby and what it currently does."""
    summaries = []
    for address_id, group in joined.groupby(address_id_col, dropna=False):
        matched = group[group["id_local"].notna()]
        activity_summary = [
            {
                "id_seccion": row["id_seccion"],
                "desc_epigrafe": row["desc_epigrafe"],
                "desc_situacion_local": row["desc_situacion_local"],
            }
            for _, row in matched.iterrows()
        ]
        is_existing_hosteleria = any(
            classify_epigrafe(row["id_seccion"], row["id_epigrafe"]).status == "mapped"
            for _, row in matched.iterrows()
        )
        summaries.append(
            {
                address_id_col: address_id,
                "geometry": group.iloc[0]["geometry"],
                "has_commercial_local": len(matched) > 0,
                "current_activity_summary": activity_summary,
                "is_existing_hosteleria_class": is_existing_hosteleria,
            }
        )
    return gpd.GeoDataFrame(summaries, geometry="geometry", crs=joined.crs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_hosteleria.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hosteleria.py tests/test_hosteleria.py
git commit -m "$(cat <<'EOF'
Add candidate address commercial-local context join

join_candidate_context nearest-joins address points to locales within
a distance tolerance, keeping unmatched addresses (left-join
semantics) rather than dropping purely-residential ones.
summarize_candidate_context collapses that into one row per address
with has_commercial_local / current_activity_summary /
is_existing_hosteleria_class.
EOF
)"
```

---

### Task 7: Reconcile script (both outputs)

**Files:**
- Create: `scripts/04_reconcile_hosteleria.py`

**Interfaces:**
- Consumes: `zpae_geometry.build_study_area` (Task 1), `hosteleria.build_competitor_layer`, `hosteleria.join_candidate_context`, `hosteleria.summarize_candidate_context` (Tasks 5-6).
- Produces: `data/processed/hosteleria_competitors_zpae_clip.gpkg`, `data/processed/candidate_addresses_zpae_clip.gpkg`.

No new unit tests (orchestration over already-tested functions) — verification is a live run.

- [ ] **Step 1: Write the reconcile script**

Create `scripts/04_reconcile_hosteleria.py`:

```python
"""
Stage 2: build the two hostelería pipeline outputs from the raw citywide
censo de locales pull (scripts/03_fetch_hosteleria.py):
  A. the ZPAE-relevant competitor point layer, clipped to the four zones.
  B. candidate-address commercial-local context, joined onto Stage 1's
     clipped rt_portalpk_p address points.

Run locally (after scripts/01, 02, and 03 have produced their outputs):
    python scripts/04_reconcile_hosteleria.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from hosteleria import (
    build_competitor_layer,
    join_candidate_context,
    summarize_candidate_context,
)
from zpae_geometry import build_study_area

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
BUFFER_M = 300
JOIN_TOLERANCE_M = 15

raw_gdf = gpd.read_file(RAW_DIR / "hosteleria" / "censo_locales_full.geojson")
records = raw_gdf.drop(columns="geometry").to_dict("records")

# --- A. Competitor layer ---
result = build_competitor_layer(records)
print(f"Competitors: {result.mapped_count} mapped, "
      f"{result.excluded_count} excluded, {result.unmapped_count} unmapped.")

zpae_ambitos = gpd.read_file(RAW_DIR / "zpae" / "zpae_ambitos.geojson")
study_area = build_study_area(zpae_ambitos, buffer_m=BUFFER_M)

competitors_clipped = result.gdf[result.gdf.intersects(study_area)]
print(f"Competitors after clip to study area: "
      f"{len(result.gdf)} -> {len(competitors_clipped)}")

competitors_out = PROCESSED_DIR / "hosteleria_competitors_zpae_clip.gpkg"
competitors_clipped.to_file(competitors_out, driver="GPKG")
print(f"Saved to {competitors_out}")

# --- B. Candidate address context ---
addresses = gpd.read_file(PROCESSED_DIR / "rt_portalpk_p_zpae_clip.gpkg")
# NOT clipped -- a local just outside the study buffer could still be the
# nearest match to an address right at the buffer edge.
locals_gdf = raw_gdf

joined = join_candidate_context(addresses, locals_gdf, tolerance_m=JOIN_TOLERANCE_M)
match_distances = joined["match_distance_m"].dropna()
print(f"\nMatch distances (m): min={match_distances.min():.1f} "
      f"median={match_distances.median():.1f} "
      f"p95={match_distances.quantile(0.95):.1f} "
      f"max={match_distances.max():.1f}")
unmatched_count = joined["id_local"].isna().sum()
print(f"Addresses with no commercial local within {JOIN_TOLERANCE_M}m: "
      f"{unmatched_count} / {len(addresses)}")

summary = summarize_candidate_context(joined, address_id_col="id_porpk")
summary["current_activity_summary"] = summary["current_activity_summary"].apply(json.dumps)

candidates_out = PROCESSED_DIR / "candidate_addresses_zpae_clip.gpkg"
summary.to_file(candidates_out, driver="GPKG")
print(f"Saved to {candidates_out}")
```

- [ ] **Step 2: Run it end-to-end against real data**

Run: `source .venv/bin/activate && python scripts/04_reconcile_hosteleria.py`

Expected:
- Competitor mapped/excluded/unmapped counts printed, unmapped should be 0 (or match the accepted gaps confirmed in Task 4).
- Competitor count after clip should be a few hundred to low thousands (much smaller than the 216,788 citywide, similar order of magnitude to Stage 1's clip ratios, e.g. `rt_tramo_vial` clipped to ~1.4% of citywide).
- Match-distance report: inspect the median and p95 values. If p95 is very close to 15m (the tolerance ceiling) rather than well below it, that's a sign 15m may be too tight and cutting off real matches — note it as a follow-up rather than silently accepting.
- "Addresses with no commercial local nearby" count: sanity-check this isn't the vast majority of the 13,876 addresses (ZPAE zones are dense commercial areas — if most addresses show no nearby local, the join tolerance or coordinate systems likely have a bug).
- Both output files exist under `data/processed/`.

- [ ] **Step 3: Commit**

```bash
git add scripts/04_reconcile_hosteleria.py
git commit -m "$(cat <<'EOF'
Add reconcile script producing both Stage 2 outputs

Builds the clipped competitor point layer and the candidate-address
commercial-local context in one pass over the citywide censo de
locales pull, reusing zpae_geometry.build_study_area for the same
300m buffer as scripts/02.
EOF
)"
```

---

### Task 8: Document findings in data_sources.md

**Files:**
- Modify: `docs/data_sources.md`

- [ ] **Step 1: Add a Stage 2 section**

Read the current file first (`docs/data_sources.md`), then append a new `## 5. Hostelería competitor data (Stage 2)` section (renumbering if needed to fit after the existing "3. Address points" / "4. Street network" sections) covering:
- The CKAN datastore API base and the four sibling resources found (`-1`, `-3`, `-5`, `-6`), with a note that only `-5` was used and why.
- The confirmed `id_situacion_local` breakdown (citywide) and the "exclude only Uso vivienda" decision.
- A pointer to `src/activities.py` for the full epígrafe mapping table rather than duplicating it in the docs (single source of truth).
- The two documented gaps (Clase III Cat.2, hotel street-access bars) and the join-tolerance open question, cross-referencing `docs/superpowers/specs/2026-07-17-stage2-hosteleria-pipeline-design.md`.

Use the same factual, source-cited style as the existing sections (see section 1's "What we actually found" writeup for the tone to match).

- [ ] **Step 2: Commit**

```bash
git add docs/data_sources.md
git commit -m "Document Stage 2 hostelería data source findings in data_sources.md"
```

---

## Post-plan verification

After Task 8, run the full test suite once more to confirm nothing regressed across tasks:

Run: `source .venv/bin/activate && pytest -v`
Expected: all tests across `test_zpae_geometry.py`, `test_activities.py`, `test_ckan.py`, `test_hosteleria.py` pass (21 tests total).
