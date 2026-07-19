# Nearest-Competitor Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every candidate address already evaluated in Stage 4, look up and record the *identity* (name, activity type, classification, distance, location) of the nearest classified competitor — both the one that determines the binding pass/fail margin and the single closest one overall — under both the strict and lenient distance interpretations.

**Architecture:** A new module `src/nearest_competitor.py` builds a `node_id -> [competitor records]` index from the existing competitors gdf, then runs one bounded Dijkstra search per candidate node over the existing Stage 3 walkable graph (`networkx.single_source_dijkstra_path_length`) to find, among reachable competitor-bearing nodes, the nearest one — optionally filtered to a classification, and computed either as pure network distance (lenient) or network distance + both endpoints' door-offsets (strict). `scripts/08_compute_distances.py` calls this four times per candidate (strict/lenient × binding/overall) and appends the results as new columns, without touching the existing `evaluate_candidate` pass/fail logic.

**Tech Stack:** Python, GeoPandas, NetworkX (the graph is a `networkx.MultiGraph` pickled by Stage 3 — edges carry a `geom` (shapely LineString) attribute, not a plain numeric weight, so distance queries need a weight function that reads `d["geom"].length`, and — because it's a MultiGraph — that function receives a `keydict` per neighbor (`{edge_key: edge_data}`), not a single edge's data), pytest.

## Global Constraints

- Competitor scope is exactly the existing Stage 2 layer (Decreto 184/1998 hostelería/ocio classes) — no new data sourcing.
- Reuse `SEARCH_CUTOFF_M = 350` (already defined in `scripts/08_compute_distances.py`) as the lookup cutoff — "not found within cutoff" means comfortably clear, not unknown, matching the existing convention.
- Candidates/competitors already carry `nearest_node_id` and `offset_distance_m` columns (Stage 3/4 snapping, see `src/network.py:snap_points_to_nearest_node`) — do not re-derive these.
- Do not modify `src/distance_engine.py`'s `evaluate_candidate` or its existing tests — this is a purely additive lookup that runs alongside it.
- New module lives at `src/nearest_competitor.py` (mirrors the existing `src/distance_engine.py` / `src/network.py` split by responsibility).
- Tests go in `tests/test_nearest_competitor.py`, following the existing test style in `tests/test_distance_engine.py` and `tests/test_network.py` (plain `networkx`/`geopandas` fixtures built inline, no shared fixture files).

---

## Task 1: `build_competitor_node_index`

**Files:**
- Create: `src/nearest_competitor.py`
- Test: `tests/test_nearest_competitor.py`

**Interfaces:**
- Produces: `build_competitor_node_index(competitors_gdf: gpd.GeoDataFrame) -> dict[str, list[dict]]`. Each dict value is a list of records (one per competitor snapped to that node), each record a plain `dict` with keys: `id_local`, `rotulo`, `desc_epigrafe`, `classification`, `offset_distance_m`, `x`, `y`.
- Consumes: a GeoDataFrame with columns `id_local`, `rotulo`, `desc_epigrafe`, `classification`, `nearest_node_id`, `offset_distance_m`, and point `geometry` (matches the columns already present on `hosteleria_competitors_zpae_tagged.gpkg` after Stages 2/4/7 — see `src/hosteleria.py:build_competitor_layer` and `src/network.py:snap_points_to_nearest_node`).

- [ ] **Step 1: Write the failing test**

```python
import geopandas as gpd
from shapely.geometry import Point

from nearest_competitor import build_competitor_node_index


def _competitors_gdf(rows):
    """rows: list of (id_local, rotulo, desc_epigrafe, classification,
    nearest_node_id, offset_distance_m, x, y) tuples."""
    records = [
        {
            "id_local": r[0], "rotulo": r[1], "desc_epigrafe": r[2],
            "classification": r[3], "nearest_node_id": r[4],
            "offset_distance_m": r[5],
        }
        for r in rows
    ]
    geometry = [Point(r[6], r[7]) for r in rows]
    return gpd.GeoDataFrame(records, geometry=geometry, crs="EPSG:25830")


def test_build_competitor_node_index_groups_by_node():
    gdf = _competitors_gdf([
        ("1", "Bar Uno", "BAR SIN COCINA", "moderada", "nodeA", 2.5, 100.0, 200.0),
        ("2", "Bar Dos", "BAR CON COCINA", "alta", "nodeA", 1.0, 101.0, 201.0),
        ("3", "Bar Tres", "CAFETERIA", "baja", "nodeB", 0.5, 300.0, 400.0),
    ])
    index = build_competitor_node_index(gdf)
    assert set(index.keys()) == {"nodeA", "nodeB"}
    assert len(index["nodeA"]) == 2
    assert len(index["nodeB"]) == 1
    record = index["nodeB"][0]
    assert record["id_local"] == "3"
    assert record["rotulo"] == "Bar Tres"
    assert record["desc_epigrafe"] == "CAFETERIA"
    assert record["classification"] == "baja"
    assert record["offset_distance_m"] == 0.5
    assert record["x"] == 300.0
    assert record["y"] == 400.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nearest_competitor.py::test_build_competitor_node_index_groups_by_node -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nearest_competitor'`

- [ ] **Step 3: Write minimal implementation**

```python
"""
Looks up the identity (name, activity type, classification, distance,
location) of the nearest classified competitor to a candidate address --
both the one that determines the binding pass/fail margin and the single
closest one overall -- under both the strict and lenient distance
interpretations already computed by src/distance_engine.py. See
docs/superpowers/specs/2026-07-19-nearest-competitor-identity-design.md.
"""

import geopandas as gpd
import networkx as nx


def build_competitor_node_index(competitors_gdf: gpd.GeoDataFrame) -> dict[str, list[dict]]:
    """Group competitors by their snapped network node, keeping the
    fields needed for identity lookup and strict/lenient distance math."""
    index: dict[str, list[dict]] = {}
    for _, row in competitors_gdf.iterrows():
        record = {
            "id_local": row["id_local"],
            "rotulo": row["rotulo"],
            "desc_epigrafe": row["desc_epigrafe"],
            "classification": row["classification"],
            "offset_distance_m": row["offset_distance_m"],
            "x": row.geometry.x,
            "y": row.geometry.y,
        }
        index.setdefault(row["nearest_node_id"], []).append(record)
    return index
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_nearest_competitor.py::test_build_competitor_node_index_groups_by_node -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nearest_competitor.py tests/test_nearest_competitor.py
git commit -m "Add competitor-node index for nearest-competitor identity lookup"
```

---

## Task 2: `find_nearest_competitor` — lenient distance, no classification filter

**Files:**
- Modify: `src/nearest_competitor.py`
- Test: `tests/test_nearest_competitor.py`

**Interfaces:**
- Consumes: `build_competitor_node_index` from Task 1 (exact dict shape above).
- Produces:
  ```python
  @dataclass(frozen=True)
  class NearestCompetitor:
      id_local: str
      rotulo: str | None
      desc_epigrafe: str
      classification: str
      distance_m: float
      x: float
      y: float

  def find_nearest_competitor(
      graph: nx.Graph,
      node_id: str,
      competitor_index: dict[str, list[dict]],
      *,
      cutoff_m: float,
      candidate_offset_m: float,
      strict: bool,
      classification_filter: str | None = None,
  ) -> NearestCompetitor | None:
  ```
  This task implements the `strict=False` path fully and the function
  signature completely; Task 3 adds the `strict=True` offset math.

Build a small synthetic graph for these tests: four nodes in a line,
`n0 -- n1 -- n2 -- n3`, each edge 10m long via a straight `geom` LineString,
so cumulative network distance from `n0` is 0, 10, 20, 30m to `n0..n3`.

- [ ] **Step 1: Write the failing test**

```python
import networkx as nx
from shapely.geometry import LineString

from nearest_competitor import find_nearest_competitor


def _line_graph():
    g = nx.MultiGraph()
    coords = {"n0": (0, 0), "n1": (10, 0), "n2": (20, 0), "n3": (30, 0)}
    for node_id, (x, y) in coords.items():
        g.add_node(node_id, x=x, y=y)
    for u, v in [("n0", "n1"), ("n1", "n2"), ("n2", "n3")]:
        (x1, y1), (x2, y2) = coords[u], coords[v]
        g.add_edge(u, v, geom=LineString([(x1, y1), (x2, y2)]))
    return g


def test_find_nearest_competitor_lenient_picks_closest_by_network_distance():
    graph = _line_graph()
    index = {
        "n2": [{
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "moderada", "offset_distance_m": 5.0, "x": 20.0, "y": 0.0,
        }],
        "n3": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 30.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
    )
    # n2 is 20m away (network), n3 is 30m away -- n2's competitor wins
    # despite its larger offset_distance_m, because lenient ignores offsets.
    assert result.id_local == "1"
    assert result.distance_m == 20.0


def test_find_nearest_competitor_respects_cutoff():
    graph = _line_graph()
    index = {
        "n3": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 30.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=25, candidate_offset_m=0.0, strict=False,
    )
    # n3 is 30m away, beyond the 25m cutoff -- nothing found.
    assert result is None


def test_find_nearest_competitor_classification_filter_excludes_non_matching():
    graph = _line_graph()
    index = {
        "n1": [{
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "alta", "offset_distance_m": 0.0, "x": 10.0, "y": 0.0,
        }],
        "n2": [{
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
        classification_filter="moderada",
    )
    # Closer competitor (n1, alta) is filtered out; moderada one at n2 wins.
    assert result.id_local == "2"
    assert result.distance_m == 20.0


def test_find_nearest_competitor_tie_break_lowest_id_local():
    graph = _line_graph()
    index = {
        "n2": [
            {
                "id_local": "9", "rotulo": "Bar Nueve", "desc_epigrafe": "CAFETERIA",
                "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
            },
            {
                "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
                "classification": "moderada", "offset_distance_m": 0.0, "x": 20.0, "y": 0.0,
            },
        ],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
    )
    assert result.id_local == "2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_nearest_competitor.py -v -k find_nearest_competitor`
Expected: FAIL with `ImportError: cannot import name 'find_nearest_competitor'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/nearest_competitor.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class NearestCompetitor:
    id_local: str
    rotulo: str | None
    desc_epigrafe: str
    classification: str
    distance_m: float
    x: float
    y: float


def _multigraph_edge_weight(u, v, keydict):
    return min(data["geom"].length for data in keydict.values())


def find_nearest_competitor(
    graph: nx.Graph,
    node_id: str,
    competitor_index: dict[str, list[dict]],
    *,
    cutoff_m: float,
    candidate_offset_m: float,
    strict: bool,
    classification_filter: str | None = None,
) -> NearestCompetitor | None:
    """Bounded Dijkstra from node_id over graph, returning the nearest
    competitor in competitor_index (optionally restricted to
    classification_filter). Distance is pure network distance (lenient)
    or network distance plus both endpoints' door-offsets (strict).
    Returns None if nothing matches within cutoff_m."""
    network_distances = nx.single_source_dijkstra_path_length(
        graph, node_id, cutoff=cutoff_m, weight=_multigraph_edge_weight,
    )

    best: NearestCompetitor | None = None
    for reachable_node, network_distance in network_distances.items():
        for record in competitor_index.get(reachable_node, []):
            if classification_filter is not None and record["classification"] != classification_filter:
                continue
            if strict:
                total_distance = network_distance + candidate_offset_m + record["offset_distance_m"]
            else:
                total_distance = network_distance
            if total_distance > cutoff_m:
                continue
            if best is None or total_distance < best.distance_m or (
                total_distance == best.distance_m and record["id_local"] < best.id_local
            ):
                best = NearestCompetitor(
                    id_local=record["id_local"],
                    rotulo=record["rotulo"],
                    desc_epigrafe=record["desc_epigrafe"],
                    classification=record["classification"],
                    distance_m=total_distance,
                    x=record["x"],
                    y=record["y"],
                )
    return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nearest_competitor.py -v`
Expected: PASS (all tests so far, including Task 1's)

- [ ] **Step 5: Commit**

```bash
git add src/nearest_competitor.py tests/test_nearest_competitor.py
git commit -m "Add find_nearest_competitor with lenient distance and classification filtering"
```

---

## Task 3: strict distance (door-offset math)

**Files:**
- Modify: `src/nearest_competitor.py` (no further changes needed — `strict=True` path was written in Task 2's implementation; this task is tests-only, to lock in the offset math against regression)
- Test: `tests/test_nearest_competitor.py`

**Interfaces:**
- Consumes: `find_nearest_competitor` from Task 2 (same signature, `strict=True` path).

- [ ] **Step 1: Write the failing test**

```python
def test_find_nearest_competitor_strict_adds_both_offsets():
    graph = _line_graph()
    index = {
        "n2": [{
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "moderada", "offset_distance_m": 5.0, "x": 20.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=3.0, strict=True,
    )
    # network distance 20m + candidate offset 3m + competitor offset 5m = 28m
    assert result.distance_m == 28.0


def test_find_nearest_competitor_strict_can_flip_which_competitor_wins():
    graph = _line_graph()
    index = {
        "n1": [{  # network 10m + huge own offset -> strict total 110m
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "moderada", "offset_distance_m": 100.0, "x": 10.0, "y": 0.0,
        }],
        "n2": [{  # network 20m + small own offset -> strict total 21m
            "id_local": "2", "rotulo": "Bar Dos", "desc_epigrafe": "CAFETERIA",
            "classification": "moderada", "offset_distance_m": 1.0, "x": 20.0, "y": 0.0,
        }],
    }
    lenient = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=False,
    )
    strict = find_nearest_competitor(
        graph, "n0", index, cutoff_m=350, candidate_offset_m=0.0, strict=True,
    )
    assert lenient.id_local == "1"   # closer by raw network distance
    assert strict.id_local == "2"    # closer once real-world offsets are included
    assert strict.distance_m == 21.0


def test_find_nearest_competitor_strict_respects_cutoff_after_offsets():
    graph = _line_graph()
    index = {
        "n2": [{  # network 20m + offsets push it just past a 25m cutoff
            "id_local": "1", "rotulo": "Bar Uno", "desc_epigrafe": "BAR SIN COCINA",
            "classification": "moderada", "offset_distance_m": 4.0, "x": 20.0, "y": 0.0,
        }],
    }
    result = find_nearest_competitor(
        graph, "n0", index, cutoff_m=25, candidate_offset_m=2.0, strict=True,
    )
    # 20 + 2 + 4 = 26m, past cutoff -- must be excluded even though the
    # raw network distance (20m) was within cutoff.
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_nearest_competitor.py -v -k strict`
Expected: `test_find_nearest_competitor_strict_respects_cutoff_after_offsets` FAILS (the Task 2 implementation includes `reachable_node` in `network_distances` if the *raw* network distance is within `cutoff_m`, which is correct — but confirm the `if total_distance > cutoff_m: continue` guard in the Task 2 code is actually present; if this test fails because that guard is missing, that's the bug this test exists to catch). The other two should already PASS from Task 2's implementation.

- [ ] **Step 3: Fix if needed**

If the cutoff-after-offsets test fails, confirm the `if total_distance > cutoff_m: continue` line is present in `find_nearest_competitor` (it was included in Task 2's implementation above — this step only applies if it was somehow dropped).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_nearest_competitor.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_nearest_competitor.py
git commit -m "Lock in strict-mode door-offset math for find_nearest_competitor"
```

---

## Task 4: Integrate into `scripts/08_compute_distances.py`

**Files:**
- Modify: `scripts/08_compute_distances.py`

**Interfaces:**
- Consumes: `build_competitor_node_index`, `find_nearest_competitor`, `NearestCompetitor` from `src/nearest_competitor.py` (Tasks 1-3).
- Produces: 24 new columns on `data/processed/distance_evaluation_results.gpkg` (see Output Schema in the design doc): for each of `strict`/`lenient` × `binding`/`overall`, columns `{prefix}_id_local`, `{prefix}_rotulo`, `{prefix}_desc_epigrafe`, `{prefix}_classification`, `{prefix}_distance_m`, `{prefix}_x`, `{prefix}_y`.

This task has no isolated unit test of its own (it's a script, exercised
by the manual smoke-check in Step 3) — Tasks 1-3 already cover
`nearest_competitor.py`'s correctness in isolation.

- [ ] **Step 1: Add the import and build the competitor index**

In `scripts/08_compute_distances.py`, add to the imports (near the existing
`from distance_engine import ...` line):

```python
from nearest_competitor import build_competitor_node_index, find_nearest_competitor
```

Immediately after the existing line
`competitors = gpd.read_file(PROCESSED_DIR / "hosteleria_competitors_zpae_tagged.gpkg")`,
add:

```python
competitor_index = build_competitor_node_index(
    competitors[competitors["classification"].notna()]
)
```

(Only classified competitors are eligible, matching `build_classification_landuse_gdf`'s
existing filter in `src/distance_engine.py`.)

- [ ] **Step 2: Compute the four lookups per candidate and add them to each result row**

In the `for _, row in evaluable.iterrows():` loop in
`scripts/08_compute_distances.py`, after the existing
`evaluation = evaluate_candidate(...)` call and before `results.append({...})`,
add:

```python
    candidate_offset_m = row["offset_distance_m"]

    def _lookup(strict, classification_filter):
        found = find_nearest_competitor(
            graph, node_id, competitor_index,
            cutoff_m=SEARCH_CUTOFF_M, candidate_offset_m=candidate_offset_m,
            strict=strict, classification_filter=classification_filter,
        )
        if found is None:
            return {"id_local": None, "rotulo": None, "desc_epigrafe": None,
                    "classification": None, "distance_m": None, "x": None, "y": None}
        return {
            "id_local": found.id_local, "rotulo": found.rotulo,
            "desc_epigrafe": found.desc_epigrafe, "classification": found.classification,
            "distance_m": found.distance_m, "x": found.x, "y": found.y,
        }

    nearest_lookups = {
        "strict_nearest_binding": _lookup(True, evaluation.strict_binding_classification),
        "lenient_nearest_binding": _lookup(False, evaluation.lenient_binding_classification),
        "strict_nearest_overall": _lookup(True, None),
        "lenient_nearest_overall": _lookup(False, None),
    }
    # Binding-classification lookups are meaningless when there's no binding
    # classification (rule doesn't apply to this street, or prohibited
    # outright) -- force them null rather than looking up an arbitrary
    # classification.
    if evaluation.strict_binding_classification is None:
        nearest_lookups["strict_nearest_binding"] = _lookup(True, "__none__")
    if evaluation.lenient_binding_classification is None:
        nearest_lookups["lenient_nearest_binding"] = _lookup(False, "__none__")
```

Note: `classification_filter="__none__"` is a deliberate sentinel that
matches no real classification key, forcing that lookup to return the
all-null dict via `_lookup`'s `found is None` branch -- simpler than a
separate null-dict helper.

- [ ] **Step 3: Flatten the lookups into the result row**

Still inside `scripts/08_compute_distances.py`'s loop, change the
`results.append({...})` call to include the new columns by flattening
`nearest_lookups`:

```python
    result_row = {
        "id_porpk": row["id_porpk"],
        "zpae_zone": row["zpae_zone"],
        "classification": row["classification"],
        "strict_pass": evaluation.strict_pass,
        "strict_margin_m": evaluation.strict_margin_m,
        "strict_binding_classification": evaluation.strict_binding_classification,
        "lenient_pass": evaluation.lenient_pass,
        "lenient_margin_m": evaluation.lenient_margin_m,
        "lenient_binding_classification": evaluation.lenient_binding_classification,
        "prohibited_outright": evaluation.prohibited_outright,
        "interpretations_disagree": evaluation.interpretations_disagree,
        "geometry": row["geometry"],
    }
    for prefix, fields in nearest_lookups.items():
        for field_name, value in fields.items():
            result_row[f"{prefix}_{field_name}"] = value
    results.append(result_row)
```

Remove the old `results.append({...})` block this replaces.

- [ ] **Step 4: Smoke-check on a small slice**

This script runs against real precomputed Stage 1-4 data files that aren't
committed to the repo (per the README's Setup section) and takes a while
over all ~9,838 candidates, so don't run the full script end-to-end as
part of this task. Instead, verify correctness with a syntax/import check
and a scoped dry run:

Run: `python -c "import ast; ast.parse(open('scripts/08_compute_distances.py').read())"`
Expected: no output (valid syntax)

If the processed data files referenced by `PROCESSED_DIR` exist locally,
additionally run:

```bash
python3 -c "
import sys
sys.path.insert(0, 'src')
sys.argv = ['08_compute_distances.py']
exec(compile(open('scripts/08_compute_distances.py').read().replace(
    'evaluable = candidates[candidates[\"zpae_zone\"].notna() & candidates[\"classification\"].notna()]',
    'evaluable = candidates[candidates[\"zpae_zone\"].notna() & candidates[\"classification\"].notna()].head(20)'
), 'scripts/08_compute_distances.py', 'exec'))
print(results_gdf[[c for c in results_gdf.columns if 'nearest' in c]].head())
"
```
Expected: prints a 20-row slice with the 24 new `*_nearest_*` columns
populated (non-null where a competitor exists within cutoff, all-null
together otherwise), and the script's existing summary print statements
still run without error.

- [ ] **Step 5: Commit**

```bash
git add scripts/08_compute_distances.py
git commit -m "Add nearest-competitor identity lookups to Stage 4 distance computation"
```

---

## Task 5: Update docs

**Files:**
- Modify: `docs/data_sources.md`
- Modify: `README.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Add a note to `docs/data_sources.md`**

Find the section documenting `distance_evaluation_results.gpkg` (Stage 4's
output) and add a short paragraph noting the new columns: for each of
strict/lenient × binding/overall, the nearest competitor's id_local,
rotulo, desc_epigrafe, classification, distance_m, x, y — null together
when nothing is found within `SEARCH_CUTOFF_M` (350m), or when the
relevant binding classification doesn't apply. Cross-reference
`docs/superpowers/specs/2026-07-19-nearest-competitor-identity-design.md`
for the full rationale.

- [ ] **Step 2: Add a line to `README.md`'s Stage 4 bullet**

In the Stage 4 bullet under `## Status`, add one sentence noting that each
candidate's result now also identifies the specific nearest competitor
(name, activity type, location) behind each distance figure, not just the
number — so the eventual UI can explain *why* an address passes or fails,
not just *whether*.

- [ ] **Step 3: Commit**

```bash
git add docs/data_sources.md README.md
git commit -m "Document nearest-competitor identity columns in Stage 4 output"
```

---

## Self-Review Notes

- **Spec coverage:** all four lookup combinations (strict/lenient ×
  binding/overall), the 24-column output schema, the null conventions, the
  competitor-scope confirmation (Task 5 doc note), and the
  `nearest_competitor.py` test list from the design doc (nearest-by-distance,
  classification filtering, strict offset math, cutoff, tie-break, `None`
  filter falling back to overall) are all covered by Tasks 1-4.
- **Placeholder scan:** none found — every step has runnable code or an
  exact command with expected output.
- **Type consistency:** `NearestCompetitor` fields (`id_local`, `rotulo`,
  `desc_epigrafe`, `classification`, `distance_m`, `x`, `y`) match across
  Task 2's dataclass, Task 4's `_lookup` dict flattening, and the design
  doc's output schema.
