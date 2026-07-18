# Stage 3 Network Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Cityseer-compatible walkable network graph from the clipped IGR-RT street segments, and snap Stage 2's competitor/candidate point layers onto it.

**Architecture:** A pure-logic module (`src/network.py`) for filtering/deduping segments and for the point-to-node snapping math, consumed by two orchestration scripts (`scripts/05_build_network_graph.py`, `scripts/06_snap_points_to_network.py`) that call the real `cityseer` library — mirrors Stage 2's fetch/reconcile-script + src-module split.

**Tech Stack:** Python, geopandas, shapely, networkx (3.6.1, confirmed installed), cityseer (5.6.1, confirmed installed), pytest.

## Global Constraints

- Native CRS is EPSG:25830 everywhere.
- Every module importable by bare name from `src/` via `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))` — no package/`__init__.py` setup.
- `data/` stays gitignored — no output files committed, only the scripts that produce them.
- All cityseer function calls in this plan were verified against the real installed library (5.6.1) via a live smoke test on 2026-07-18, not guessed from documentation — do not "improve" or "simplify" the call sequence without re-verifying against the real library first, since prior guesses (e.g. an assumed `nx_simple_geoms` step) turned out to be wrong/unnecessary.
- Underground segments (`situacion == 2`) must be excluded from the walkable network regardless of their vehicle-access tag — confirmed via manual inspection these are real Madrid car tunnels (Princesa, Bailén, San Vicente, the A-5/A-6/M-30 ring), not places pedestrians walk, even though most are mistagged `Peatón+bici+vehículo`.
- The graph is undirected — `sentido` (one-way/two-way) is a vehicle-routing attribute, not a pedestrian one; the Normativa itself measures distance "door to door along the axis of streets," not vehicle routing.
- Decomposition max length is 10m (confirmed with the project owner: tight enough given other error sources in the pipeline already exceed the resulting ~5m worst-case snapping offset; 5m was considered and rejected as doubling graph size for a smaller-than-existing-error-margin gain).

---

## File Structure

- `src/network.py` (new) — `filter_walkable()`, `dedupe_by_id_tramo()`, `nodes_gdf_from_graph()`, `snap_points_to_nearest_node()`.
- `scripts/05_build_network_graph.py` (new) — loads the clipped street network, filters/dedupes, builds and decomposes the Cityseer graph, saves it.
- `scripts/06_snap_points_to_network.py` (new) — loads the Stage 3 graph and Stage 2's point layers, snaps them, saves the results.
- `requirements.txt` (modify) — add `cityseer`, `networkx`.

---

### Task 1: Segment filtering and deduplication

**Files:**
- Create: `src/network.py`
- Create: `tests/test_network.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `network.filter_walkable(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame`, `network.dedupe_by_id_tramo(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame` — both used by Task 2's `scripts/05_build_network_graph.py`.

- [ ] **Step 1: Add networkx and cityseer to requirements.txt**

Edit `requirements.txt` to:

```
geopandas
fiona
pyogrio
shapely
requests
pytest
networkx
cityseer
```

- [ ] **Step 2: Install and verify**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: successful install (networkx/cityseer are new; everything else already satisfied).

- [ ] **Step 3: Write the failing tests**

Create `tests/test_network.py`:

```python
import geopandas as gpd
from shapely.geometry import LineString

from network import dedupe_by_id_tramo, filter_walkable


def _segments_gdf(rows):
    """rows: list of (id_tramo, situacion, tipovehic, clase) tuples."""
    ids, sits, vehics, clases = zip(*rows)
    return gpd.GeoDataFrame(
        {
            "id_tramo": list(ids),
            "situacion": list(sits),
            "tipovehic": list(vehics),
            "clase": list(clases),
        },
        geometry=[LineString([(0, 0), (10, 0)]) for _ in rows],
        crs="EPSG:25830",
    )


def test_filter_walkable_drops_underground():
    # situacion == 2 is Subterraneo -- real car tunnels, mistagged as
    # pedestrian-accessible in the source data (see Global Constraints).
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 2, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_drops_vehicle_only():
    # tipovehic has a trailing space in the real source data ("001 ", not
    # "001") -- the filter must handle that, not assume it's stripped.
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 1, "001 ", 1002)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_keeps_elevated():
    # situacion == 3 is Elevado -- real pedestrian viaducts, kept.
    gdf = _segments_gdf([("1", 3, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_filter_walkable_keeps_surface():
    gdf = _segments_gdf([("1", 1, "111 ", 2000)])
    result = filter_walkable(gdf)
    assert list(result["id_tramo"]) == ["1"]


def test_dedupe_by_id_tramo_keeps_first():
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("1", 1, "111 ", 2000)])
    result = dedupe_by_id_tramo(gdf)
    assert len(result) == 1


def test_dedupe_by_id_tramo_keeps_distinct():
    gdf = _segments_gdf([("1", 1, "111 ", 2000), ("2", 1, "111 ", 2000)])
    result = dedupe_by_id_tramo(gdf)
    assert len(result) == 2
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_network.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'network'`

- [ ] **Step 5: Implement the filter and dedup functions**

Create `src/network.py`:

```python
"""
Builds Stage 3's Cityseer-compatible walkable network graph from the
clipped IGR-RT street segments, and snaps Stage 2's point layers onto it.
See docs/superpowers/specs/2026-07-18-stage3-network-graph-design.md.
"""

import geopandas as gpd
from shapely.geometry import Point


def filter_walkable(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop segments that aren't real pedestrian routes: underground
    tunnels (situacion == 2 -- confirmed via manual inspection to be real
    Madrid car tunnels such as Princesa, Bailen, San Vicente, and the
    A-5/A-6/M-30 ring, even though most are mistagged as
    pedestrian-accessible), vehicle-only segments, and motorway-class
    segments. Elevated segments (situacion == 3, e.g. real pedestrian
    viaducts) and surface segments (situacion == 1) are kept."""
    walkable = gdf["situacion"] != 2
    walkable &= gdf["tipovehic"].str.strip() != "001"
    walkable &= gdf["clase"] != 1002
    return gdf[walkable]


def dedupe_by_id_tramo(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """rt_tramo_vial joins segments to street names, so a segment shared
    by two named streets appears as two identical-geometry rows under the
    same id_tramo. Keep one row per physical segment, or the graph would
    double-count these edges."""
    return gdf.drop_duplicates(subset="id_tramo", keep="first")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_network.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/network.py tests/test_network.py
git commit -m "$(cat <<'EOF'
Add walkable-network filter and id_tramo dedup

filter_walkable drops underground tunnels (mistagged as pedestrian-
accessible in the source data but confirmed to be real car tunnels),
vehicle-only segments, and motorway-class segments. dedupe_by_id_tramo
removes the street-name-join duplicates rt_tramo_vial produces.
EOF
)"
```

---

### Task 2: Build and decompose the network graph

**Files:**
- Create: `scripts/05_build_network_graph.py`

**Interfaces:**
- Consumes: `network.filter_walkable`, `network.dedupe_by_id_tramo` (Task 1).
- Produces: `data/processed/network_graph_zpae.pickle` (a pickled `networkx.MultiGraph`, decomposed at 10m) — consumed by Task 4's `scripts/06_snap_points_to_network.py`.

This is an I/O orchestration script over the real `cityseer` library, run against real data already on disk from Stage 1 (`data/processed/rt_tramo_vial_zpae_clip.gpkg`). No new unit tests — same pattern as `scripts/01_fetch_zpae.py` / `scripts/03_fetch_hosteleria.py`. Verification is running it and inspecting the printed diagnostics.

- [ ] **Step 1: Write the script**

Create `scripts/05_build_network_graph.py`:

```python
"""
Stage 3: build the walkable Cityseer-compatible network graph from the
clipped IGR-RT street segments (Stage 1's rt_tramo_vial_zpae_clip.gpkg).

Run locally (after scripts/01 and 02 have produced their outputs):
    python scripts/05_build_network_graph.py
"""

import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cityseer.tools.graphs as graphs
import cityseer.tools.io as cs_io
import geopandas as gpd
import networkx as nx

from network import dedupe_by_id_tramo, filter_walkable

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DECOMPOSE_MAX_M = 10

raw = gpd.read_file(PROCESSED_DIR / "rt_tramo_vial_zpae_clip.gpkg")
print(f"Loaded {len(raw)} segments.")

walkable = filter_walkable(raw)
print(f"After walkability filter: {len(raw)} -> {len(walkable)}")

deduped = dedupe_by_id_tramo(walkable)
print(f"After id_tramo dedup: {len(walkable)} -> {len(deduped)}")

# nx_from_generic_geopandas builds the graph directly from segment
# geometry -- no relation table needed (none exists in this download; see
# design doc). nx_remove_filler_nodes then merges degree-2 nodes
# (intermediate points that aren't real junctions) into single edges,
# retaining the merged edge's full path geometry.
base_graph = cs_io.nx_from_generic_geopandas(deduped)
base_graph = graphs.nx_remove_filler_nodes(base_graph)
print(f"Base graph: {base_graph.number_of_nodes()} nodes, "
      f"{base_graph.number_of_edges()} edges.")

components = list(nx.connected_components(base_graph))
print(f"Connected components: {len(components)}")
if len(components) > 1:
    sizes = sorted((len(c) for c in components), reverse=True)
    print(f"[!] Network is NOT fully connected -- component sizes: {sizes}. "
          f"An address in a smaller component cannot reach venues in a "
          f"different component at all via this graph. Investigate before "
          f"trusting Stage 4 results for addresses in the smaller "
          f"components (e.g. inspect their node coordinates to see which "
          f"zone they fall in and why they're cut off).")

# nx_decompose splits long edges into ~10m pieces along their real path
# length (not straight-line distance), so nodes exist roughly every 10m
# along every street -- this is what makes nearest-node snapping (Task 3)
# accurate enough for our tightest 30m threshold.
decomposed_graph = graphs.nx_decompose(base_graph, decompose_max=DECOMPOSE_MAX_M)
print(f"Decomposed graph ({DECOMPOSE_MAX_M}m): "
      f"{decomposed_graph.number_of_nodes()} nodes, "
      f"{decomposed_graph.number_of_edges()} edges.")

out_path = PROCESSED_DIR / "network_graph_zpae.pickle"
with open(out_path, "wb") as f:
    pickle.dump(decomposed_graph, f)
print(f"Saved to {out_path}")
```

- [ ] **Step 2: Run it against the real data**

Run: `source .venv/bin/activate && python scripts/05_build_network_graph.py`

Expected:
- Segment counts shrink at each filter step (starting from 4,380).
- `Connected components: 1` is the ideal outcome. If more than one component is reported, do NOT treat this as a script bug to silently fix — read the printed component sizes, inspect where the smaller component(s) are (e.g. `list(base_graph.nodes(data=True))` filtered to the small component's node keys, cross-referenced against the zone boundaries), and bring the finding back for a decision rather than proceeding as if it didn't happen.
- Decomposed graph should have substantially more nodes/edges than the base graph (each original edge split into ~10m pieces).
- `data/processed/network_graph_zpae.pickle` exists after the run.

- [ ] **Step 3: Commit**

```bash
git add scripts/05_build_network_graph.py
git commit -m "$(cat <<'EOF'
Add network graph build script

Builds the walkable graph directly from segment geometry (no relation
table exists in the source download), checks connectivity before
decomposing, and decomposes at 10m via cityseer's nx_decompose so
later point-snapping has ~5m worst-case accuracy.
EOF
)"
```

---

### Task 3: Point-to-node snapping

**Files:**
- Modify: `src/network.py`
- Modify: `tests/test_network.py`

**Interfaces:**
- Consumes: nothing new (pure module additions).
- Produces: `network.nodes_gdf_from_graph(graph: networkx.MultiGraph, crs: str) -> geopandas.GeoDataFrame`, `network.snap_points_to_nearest_node(points_gdf: geopandas.GeoDataFrame, nodes_gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame` — both used by Task 4's `scripts/06_snap_points_to_network.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_network.py`:

```python
import networkx as nx
from shapely.geometry import Point

from network import nodes_gdf_from_graph, snap_points_to_nearest_node


def test_nodes_gdf_from_graph():
    g = nx.MultiGraph()
    g.add_node("x0.0-y0.0", x=0.0, y=0.0)
    g.add_node("x10.0-y0.0", x=10.0, y=0.0)

    result = nodes_gdf_from_graph(g, crs="EPSG:25830")

    assert len(result) == 2
    assert set(result["node_id"]) == {"x0.0-y0.0", "x10.0-y0.0"}
    assert result.crs.to_string() == "EPSG:25830"


def test_snap_points_to_nearest_node():
    nodes_gdf = gpd.GeoDataFrame(
        {"node_id": ["n1", "n2"]},
        geometry=[Point(0, 0), Point(100, 100)],
        crs="EPSG:25830",
    )
    points_gdf = gpd.GeoDataFrame(
        {"point_id": ["p1"]},
        geometry=[Point(3, 4)],  # distance 5 from n1 (3-4-5 triangle)
        crs="EPSG:25830",
    )

    result = snap_points_to_nearest_node(points_gdf, nodes_gdf)

    assert result.iloc[0]["nearest_node_id"] == "n1"
    assert result.iloc[0]["offset_distance_m"] == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_network.py -v`
Expected: FAIL with `ImportError: cannot import name 'nodes_gdf_from_graph'`

- [ ] **Step 3: Implement the snapping functions**

Append to `src/network.py`:

```python
def nodes_gdf_from_graph(graph, crs: str) -> gpd.GeoDataFrame:
    """Extract a graph's nodes as a point GeoDataFrame, keyed by the
    networkx node id (a string like 'x123.4-y456.7' for cityseer-built
    graphs)."""
    records = [
        {"node_id": node_id, "geometry": Point(data["x"], data["y"])}
        for node_id, data in graph.nodes(data=True)
    ]
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def snap_points_to_nearest_node(
    points_gdf: gpd.GeoDataFrame, nodes_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Snap every point to its nearest graph node. Returns points_gdf with
    two new columns: nearest_node_id, offset_distance_m -- Stage 4 adds
    this offset back into the final network-distance calculation rather
    than dropping that precision."""
    joined = gpd.sjoin_nearest(
        points_gdf, nodes_gdf[["node_id", "geometry"]],
        how="left", distance_col="offset_distance_m",
    )
    joined = joined.rename(columns={"node_id": "nearest_node_id"})
    return joined.drop(columns=["index_right"], errors="ignore")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_network.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/network.py tests/test_network.py
git commit -m "$(cat <<'EOF'
Add point-to-nearest-node snapping

nodes_gdf_from_graph extracts a graph's nodes as a point layer.
snap_points_to_nearest_node finds each point's nearest node and
records the offset distance, so Stage 4 can add it back into the
final network-distance calculation instead of dropping that precision.
EOF
)"
```

---

### Task 4: Snap Stage 2's point layers onto the graph

**Files:**
- Create: `scripts/06_snap_points_to_network.py`

**Interfaces:**
- Consumes: `network.nodes_gdf_from_graph`, `network.snap_points_to_nearest_node` (Task 3).
- Produces: `data/processed/hosteleria_competitors_snapped.gpkg`, `data/processed/candidate_addresses_snapped.gpkg`.

No new unit tests (orchestration over already-tested functions, real data) — verification is a live run.

- [ ] **Step 1: Write the script**

Create `scripts/06_snap_points_to_network.py`:

```python
"""
Stage 3: snap Stage 2's competitor and candidate-address point layers onto
the Stage 3 decomposed network graph.

Run locally (after scripts/05_build_network_graph.py has produced its
output):
    python scripts/06_snap_points_to_network.py
"""

import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from network import nodes_gdf_from_graph, snap_points_to_nearest_node

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CRS = "EPSG:25830"

with open(PROCESSED_DIR / "network_graph_zpae.pickle", "rb") as f:
    graph = pickle.load(f)

nodes_gdf = nodes_gdf_from_graph(graph, crs=CRS)
print(f"Graph has {len(nodes_gdf)} nodes available for snapping.")

for name, filename in (
    ("competitors", "hosteleria_competitors_zpae_clip.gpkg"),
    ("candidates", "candidate_addresses_zpae_clip.gpkg"),
):
    points = gpd.read_file(PROCESSED_DIR / filename)
    snapped = snap_points_to_nearest_node(points, nodes_gdf)

    offsets = snapped["offset_distance_m"]
    print(f"\n{name}: {len(snapped)} points snapped. "
          f"Offset distance (m): min={offsets.min():.1f} "
          f"median={offsets.median():.1f} p95={offsets.quantile(0.95):.1f} "
          f"max={offsets.max():.1f}")

    out_name = filename.replace("_clip.gpkg", "_snapped.gpkg")
    out_path = PROCESSED_DIR / out_name
    snapped.to_file(out_path, driver="GPKG")
    print(f"Saved to {out_path}")
```

- [ ] **Step 2: Run it against the real data**

Run: `source .venv/bin/activate && python scripts/06_snap_points_to_network.py`

Expected:
- Both point layers report snapped counts matching Stage 2's output counts (5,341 competitors, 13,876 candidates).
- Offset distances should mostly be small (median well under 10m, matching the 10m decomposition — a p95 anywhere near or above 10m would suggest the decomposition or the snapping join isn't working as expected and needs investigation before trusting it).
- Both output `.gpkg` files exist under `data/processed/`.

- [ ] **Step 3: Commit**

```bash
git add scripts/06_snap_points_to_network.py
git commit -m "$(cat <<'EOF'
Add point-snapping script for competitors and candidate addresses

Snaps both Stage 2 point layers onto the Stage 3 decomposed graph's
nearest nodes, reporting the offset-distance distribution as a sanity
check that the 10m decomposition is producing the expected accuracy.
EOF
)"
```

---

## Post-plan verification

After Task 4, run the full test suite once more to confirm nothing regressed:

Run: `source .venv/bin/activate && pytest -v`
Expected: all tests across `test_zpae_geometry.py`, `test_activities.py`, `test_ckan.py`, `test_hosteleria.py`, `test_network.py` pass (31 tests total: 23 from Stage 1/2 + 8 new).
