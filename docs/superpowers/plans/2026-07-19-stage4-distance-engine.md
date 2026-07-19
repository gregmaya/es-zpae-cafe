# Stage 4 Distance Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute network distance from every candidate address to the nearest relevant competitor (by classification), under both a strict and lenient interpretation of the legal text, and evaluate each against its zone's threshold rule.

**Architecture:** Two new numbered scripts continuing the established convention, backed by two pure-logic modules (`src/zone_tagging.py`, `src/distance_engine.py`) that hold everything testable without real geospatial data or the cityseer library.

**Tech Stack:** Python, geopandas, cityseer 5.6.1, networkx, pytest. Same venv as prior stages.

## Global Constraints

- Native CRS is EPSG:25830 everywhere.
- Every module importable by bare name from `src/` via the repo's established `sys.path.insert` convention.
- Classification values are normalized to `alta`/`moderada`/`baja`/`sin_superacion` (matching `src/zones.py`'s `ClassificationRule` dict keys) as early as possible — never carry the raw Spanish `Clasifica` text (`"Alta"`, `"Sin superación de objetivos por ocio"`, etc.) past the tagging step.
- **Tie-breaking rule**: when a point is equidistant to street segments of different classifications (or when a source dataset has duplicate rows for the same real-world entity — a genuine issue found in Stage 2's competitor data, see below), keep the MOST RESTRICTIVE classification (alta > moderada > baja > sin_superacion). This is grounded in Art. 6 of every zone's Normativa: "en el caso de actividades que tengan accesos para el público en zonas de distinta clasificación del grado de contaminación, el régimen normativo será el correspondiente a la zona más restrictiva."
- **Confirmed real data-quality finding**: `hosteleria_competitors_zpae_snapped.gpkg` has 5,341 rows but only 5,001 unique `id_local` values — 308 businesses have multiple identical rows (same coordinates, same everything), traced to Stage 2's census source data having repeat records for the same business. This is a genuine Stage 2-origin issue, not something to fix by reopening Stage 2 (low impact: doesn't affect nearest-distance correctness since duplicate rows sit at identical positions, only inflates count-style metrics this project doesn't use). The tie-breaking dedup in this stage's tagging step absorbs it as a side effect — document this, don't silently rely on it without a trace.
- **Cross-zone competitors count** (confirmed interpretive decision): a candidate's own zone determines which rule applies, but the competitor search is NOT restricted to that same zone — any competitor within range, classified by its own street regardless of zone, counts. This means candidates and competitors are gated differently: a candidate needs BOTH `zpae_zone` (confirmed inside a zone polygon) AND `classification` (a nearby classified street) to be evaluated at all; a competitor only needs `classification` — its own zone membership is not consulted anywhere in the evaluation logic.
- **Strict vs. lenient interpretation** (confirmed interpretive decision, both computed and reported, neither silently chosen): strict = network distance + candidate's own Stage-3 `offset_distance_m` + competitor's own real-position offset (folded in automatically by cityseer). Lenient = network distance only, using synthetic competitor points at their Stage-3 `nearest_node_id` coordinates (offset zero by construction) and no candidate-side offset added.

---

## File Structure

- `src/zone_tagging.py` (new) — `tag_zone_membership()`, `tag_street_classification()`, plus the `CLASIFICA_TO_KEY` normalization map and `MAX_CLASSIFICATION_DISTANCE_M` constant.
- `scripts/07_tag_zones_and_classifications.py` (new) — orchestration: tags both point layers, saves `*_tagged.gpkg` outputs.
- `src/distance_engine.py` (new) — `EvaluationResult` dataclass, `evaluate_candidate()`, `build_classification_landuse_gdf()`, `build_lenient_competitor_points()`.
- `scripts/08_compute_distances.py` (new) — orchestration: runs the two `compute_accessibilities` passes, evaluates every in-scope candidate, saves the results table.

---

### Task 1: Zone and street-classification tagging (pure logic)

**Files:**
- Create: `src/zone_tagging.py`
- Create: `tests/test_zone_tagging.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `zone_tagging.tag_zone_membership(points_gdf: geopandas.GeoDataFrame, ambitos_gdf: geopandas.GeoDataFrame, id_col: str) -> geopandas.GeoDataFrame` (adds a `zpae_zone` column, `NaN` if outside all zones), `zone_tagging.tag_street_classification(points_gdf: geopandas.GeoDataFrame, clasificacion_gdf: geopandas.GeoDataFrame, id_col: str, max_distance_m: float = MAX_CLASSIFICATION_DISTANCE_M) -> geopandas.GeoDataFrame` (adds a `classification` column with normalized keys, `NaN` beyond tolerance), `zone_tagging.MAX_CLASSIFICATION_DISTANCE_M` (= 30), `zone_tagging.CLASIFICA_TO_KEY` (dict) — all used by Task 2's `scripts/07_tag_zones_and_classifications.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_zone_tagging.py`:

```python
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from zone_tagging import tag_street_classification, tag_zone_membership


def _ambitos_gdf():
    return gpd.GeoDataFrame(
        {"ZPAE": ["ZPAE Centro"]},
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:25830",
    )


def test_tag_zone_membership_inside():
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 50)], crs="EPSG:25830")
    result = tag_zone_membership(points, _ambitos_gdf(), id_col="id")
    assert result.iloc[0]["zpae_zone"] == "ZPAE Centro"


def test_tag_zone_membership_outside():
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(500, 500)], crs="EPSG:25830")
    result = tag_zone_membership(points, _ambitos_gdf(), id_col="id")
    assert pd.isna(result.iloc[0]["zpae_zone"])


def test_tag_street_classification_within_tolerance():
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Alta"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 5)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id")
    assert result.iloc[0]["classification"] == "alta"


def test_tag_street_classification_beyond_max_distance():
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Alta"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(50, 100)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id", max_distance_m=30)
    assert pd.isna(result.iloc[0]["classification"])


def test_tag_street_classification_breaks_ties_by_restrictiveness():
    # two equidistant lines with different classifications -- confirmed
    # this happens in real data (see docs/data_sources.md)
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Baja", "Alta"]},
        geometry=[LineString([(0, 0), (0, 100)]), LineString([(20, 0), (20, 100)])],
        crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame({"id": ["p1"]}, geometry=[Point(10, 50)], crs="EPSG:25830")
    result = tag_street_classification(points, clasif, id_col="id")
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"  # more restrictive wins the tie


def test_tag_street_classification_dedupes_duplicate_input_rows():
    # mirrors the real Stage 2 data-quality issue: one id, several
    # identical rows (see docs/data_sources.md)
    clasif = gpd.GeoDataFrame(
        {"Clasifica": ["Moderada"]}, geometry=[LineString([(0, 0), (100, 0)])], crs="EPSG:25830",
    )
    points = gpd.GeoDataFrame(
        {"id": ["dup", "dup", "dup"]},
        geometry=[Point(50, 5), Point(50, 5), Point(50, 5)],
        crs="EPSG:25830",
    )
    result = tag_street_classification(points, clasif, id_col="id")
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_zone_tagging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zone_tagging'`

- [ ] **Step 3: Implement the tagging functions**

Create `src/zone_tagging.py`:

```python
"""
Tags candidate/competitor points with their ZPAE zone (point-in-polygon
against zpae_ambitos.geojson) and street classification (nearest-line
match against zpae_clasificacion.geojson, normalized to the same
alta/moderada/baja/sin_superacion keys used in src/zones.py). See
docs/superpowers/specs/2026-07-19-stage4-distance-engine-design.md.
"""

import geopandas as gpd

MAX_CLASSIFICATION_DISTANCE_M = 30

# Normalizes zpae_clasificacion.geojson's Spanish "Clasifica" text to the
# same snake_case keys used in src/zones.py's ClassificationRule dicts.
CLASIFICA_TO_KEY = {
    "Alta": "alta",
    "Moderada": "moderada",
    "Baja": "baja",
    "Sin superación de objetivos por ocio": "sin_superacion",
}

# Art. 6 of every zone's Normativa: when an activity has public access on
# streets of different classification, the applicable regime is the most
# restrictive one. Used to break ties when a point is equidistant to two
# differently-classified street segments -- and, as a side effect,
# resolves a real Stage 2 data-quality issue where some competitors have
# multiple identical rows in the source census data (see
# docs/data_sources.md). Lower rank = more restrictive = kept.
_RESTRICTIVENESS_RANK = {"alta": 0, "moderada": 1, "baja": 2, "sin_superacion": 3}


def tag_zone_membership(
    points_gdf: gpd.GeoDataFrame, ambitos_gdf: gpd.GeoDataFrame, id_col: str
) -> gpd.GeoDataFrame:
    """Tag each point with the ZPAE zone it falls inside (ambitos_gdf's
    'ZPAE' column, matching src/zones.py's ZpaeZone.name spelling), or
    NaN if it's outside all four zone polygons -- e.g. in Stage 1's 300m
    buffer margin, where no ZPAE distance rule applies at all."""
    joined = gpd.sjoin(
        points_gdf, ambitos_gdf[["ZPAE", "geometry"]],
        how="left", predicate="within",
    )
    joined = joined.drop_duplicates(subset=id_col, keep="first")
    joined = joined.rename(columns={"ZPAE": "zpae_zone"})
    return joined.drop(columns=["index_right"], errors="ignore")


def tag_street_classification(
    points_gdf: gpd.GeoDataFrame,
    clasificacion_gdf: gpd.GeoDataFrame,
    id_col: str,
    max_distance_m: float = MAX_CLASSIFICATION_DISTANCE_M,
) -> gpd.GeoDataFrame:
    """Tag each point with the classification of its nearest classified
    street segment, normalized to alta/moderada/baja/sin_superacion, or
    NaN beyond max_distance_m. Confirmed against real data that
    zone-interior points are almost always within a few metres of a
    classified street (median 4.2m in the real candidate dataset), so
    30m is a generous cutoff, not a tight one.

    sjoin_nearest can return more than one row per input point when
    multiple lines are equidistant, or when the input itself already has
    duplicate rows for the same id. Both cases are resolved the same
    way: keep the most restrictive classification (Art. 6)."""
    joined = gpd.sjoin_nearest(
        points_gdf, clasificacion_gdf[["Clasifica", "geometry"]],
        how="left", max_distance=max_distance_m,
        distance_col="dist_to_classified_street",
    )
    joined["classification"] = joined["Clasifica"].map(CLASIFICA_TO_KEY)
    joined["_rank"] = joined["classification"].map(_RESTRICTIVENESS_RANK)
    joined = joined.sort_values("_rank", na_position="last")
    joined = joined.drop_duplicates(subset=id_col, keep="first")
    return joined.drop(columns=["Clasifica", "_rank", "index_right"], errors="ignore")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_zone_tagging.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/zone_tagging.py tests/test_zone_tagging.py
git commit -m "$(cat <<'EOF'
Add zone membership and street classification tagging

tag_zone_membership does a point-in-polygon test against the four
ZPAE zone boundaries; tag_street_classification does a nearest-line
match against the per-street classification layer, normalizing to the
same keys src/zones.py's rules use. Ties (real geometric ties, or
duplicate rows in the source data) are broken by keeping the most
restrictive classification, per Art. 6 of every zone's Normativa.
EOF
)"
```

---

### Task 2: Zone/classification tagging script

**Files:**
- Create: `scripts/07_tag_zones_and_classifications.py`

**Interfaces:**
- Consumes: `zone_tagging.tag_zone_membership`, `zone_tagging.tag_street_classification`, `zone_tagging.MAX_CLASSIFICATION_DISTANCE_M` (Task 1).
- Produces: `data/processed/candidate_addresses_zpae_tagged.gpkg`, `data/processed/hosteleria_competitors_zpae_tagged.gpkg` — consumed by Task 5's `scripts/08_compute_distances.py`.

No new unit tests (orchestration over already-tested functions, real data) — verification is a live run.

- [ ] **Step 1: Write the script**

Create `scripts/07_tag_zones_and_classifications.py`:

```python
"""
Stage 4: tag every candidate address and competitor point with its ZPAE
zone (point-in-polygon) and street classification (nearest classified
street segment, normalized to alta/moderada/baja/sin_superacion).

Run locally (after scripts/01, 02, 05, 06 have produced their outputs):
    python scripts/07_tag_zones_and_classifications.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import geopandas as gpd

from zone_tagging import (
    MAX_CLASSIFICATION_DISTANCE_M,
    tag_street_classification,
    tag_zone_membership,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

ambitos = gpd.read_file(RAW_DIR / "zpae" / "zpae_ambitos.geojson")
clasificacion = gpd.read_file(RAW_DIR / "zpae" / "zpae_clasificacion.geojson")

for name, filename, id_col in (
    ("candidates", "candidate_addresses_zpae_snapped.gpkg", "id_porpk"),
    ("competitors", "hosteleria_competitors_zpae_snapped.gpkg", "id_local"),
):
    points = gpd.read_file(PROCESSED_DIR / filename)
    n_input = len(points)
    n_unique_ids = points[id_col].nunique()
    if n_unique_ids != n_input:
        print(f"[!] {name}: {n_input} rows but only {n_unique_ids} unique "
              f"{id_col} values -- {n_input - n_unique_ids} duplicate rows "
              f"in the source data will be collapsed to one during "
              f"tagging (see docs/data_sources.md).")

    tagged = tag_zone_membership(points, ambitos, id_col=id_col)
    tagged = tag_street_classification(tagged, clasificacion, id_col=id_col)

    n_total = len(tagged)
    n_in_zone = tagged["zpae_zone"].notna().sum()
    n_classified = tagged["classification"].notna().sum()
    n_evaluable = (tagged["zpae_zone"].notna() & tagged["classification"].notna()).sum()
    print(f"{name}: {n_total} total, {n_in_zone} inside a ZPAE zone, "
          f"{n_classified} matched to a classified street (within "
          f"{MAX_CLASSIFICATION_DISTANCE_M}m), {n_evaluable} have both "
          f"(fully taggable).")

    out_path = PROCESSED_DIR / filename.replace("_snapped.gpkg", "_tagged.gpkg")
    tagged.to_file(out_path, driver="GPKG")
    print(f"  Saved to {out_path}")
```

- [ ] **Step 2: Run it against the real data**

Run: `source .venv/bin/activate && python scripts/07_tag_zones_and_classifications.py`

Expected (verified against the real data before writing this plan):
- `[!] candidates:` warning should NOT appear (candidates have no duplicate `id_porpk` in the real data).
- `[!] competitors: 5341 rows but only 5001 unique id_local values -- 340 duplicate rows...` SHOULD appear (this is real and expected, not a bug — see the Global Constraints note).
- candidates: `13876 total, 9926 inside a ZPAE zone, ... matched to a classified street, 9838 have both (fully taggable)`.
- competitors: `5001 total, 3776 inside a ZPAE zone, ... matched to a classified street, 3765 have both`. Note competitors' "matched to a classified street" count (3893) will be HIGHER than "inside a ZPAE zone" (3776) — this is expected and correct: some competitors sit just outside a zone polygon but within 30m of a classified street belonging to an adjacent zone (128 of them). Per the cross-zone-competitors-count decision, these SHOULD still be usable as competitors in Task 5 (gated on `classification`, not `zpae_zone`) — do not "fix" this by excluding them.
- Both output `.gpkg` files exist under `data/processed/` after the run.

If the exact numbers differ meaningfully from these (not just off by a handful from minor floating-point/version differences), stop and investigate before proceeding — these were computed directly against the real Stage 1-3 outputs already on disk.

- [ ] **Step 3: Commit**

```bash
git add scripts/07_tag_zones_and_classifications.py
git commit -m "$(cat <<'EOF'
Add zone/classification tagging script

Tags both candidate and competitor point layers with their ZPAE zone
and street classification. Surfaces the real duplicate-id_local
finding in competitors (traced to Stage 2's source census data) as a
loud warning rather than silently absorbing it.
EOF
)"
```

---

### Task 3: Rule evaluation (pure logic)

**Files:**
- Create: `src/distance_engine.py`
- Create: `tests/test_distance_engine.py`

**Interfaces:**
- Consumes: `zones.ClassificationRule` (already exists in `src/zones.py` from Stage 1 — fields: `prohibited_outright: bool`, `prohibited_with_music: bool`, `min_distance_m: dict[str, int] | None`).
- Produces: `distance_engine.EvaluationResult` (dataclass), `distance_engine.evaluate_candidate(own_classification: str, zone_rules: dict, strict_distances: dict, lenient_distances: dict) -> EvaluationResult` — used by Task 5's `scripts/08_compute_distances.py`.

This task has no geopandas or cityseer dependency at all — pure Python given already-known distances, so it's fully unit-testable without any real data.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_distance_engine.py`:

```python
from distance_engine import evaluate_candidate
from zones import ClassificationRule


def test_evaluate_candidate_prohibited_outright():
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("alta", zone_rules, strict_distances={}, lenient_distances={})
    assert result.prohibited_outright is True
    assert result.strict_pass is False
    assert result.lenient_pass is False


def test_evaluate_candidate_classification_not_in_rules_is_unregulated():
    # e.g. sin_superacion in most zones -- not mentioned in the rules
    # dict at all, meaning no ZPAE distance rule applies to it
    zone_rules = {"alta": ClassificationRule(prohibited_outright=True)}
    result = evaluate_candidate("sin_superacion", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.lenient_pass is True
    assert result.prohibited_outright is False


def test_evaluate_candidate_passes_when_all_competitors_far():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 90, "baja": 60},
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    # margins: alta 150-100=50, moderada 90-75=15, baja 60-50=10 -> baja binds
    assert result.strict_pass is True
    assert result.strict_margin_m == 10
    assert result.strict_binding_classification == "baja"


def test_evaluate_candidate_fails_when_a_competitor_too_close():
    zone_rules = {
        "moderada": ClassificationRule(min_distance_m={"alta": 100, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate(
        "moderada", zone_rules,
        strict_distances={"alta": 150, "moderada": 60, "baja": 60},  # moderada margin = -15
        lenient_distances={"alta": 150, "moderada": 90, "baja": 60},
    )
    assert result.strict_pass is False
    assert result.strict_margin_m == -15
    assert result.strict_binding_classification == "moderada"
    assert result.lenient_pass is True
    assert result.interpretations_disagree is True


def test_evaluate_candidate_no_competitor_found_within_search_range():
    zone_rules = {
        "baja": ClassificationRule(min_distance_m={"alta": 150, "moderada": 75, "baja": 50}),
    }
    result = evaluate_candidate("baja", zone_rules, strict_distances={}, lenient_distances={})
    assert result.strict_pass is True
    assert result.strict_margin_m is None
    assert result.lenient_pass is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_distance_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'distance_engine'`

- [ ] **Step 3: Implement the rule-evaluation logic**

Create `src/distance_engine.py`:

```python
"""
Evaluates a candidate address's classification against its zone's
threshold rule, given precomputed nearest-competitor distances per
classification. See
docs/superpowers/specs/2026-07-19-stage4-distance-engine-design.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationResult:
    strict_pass: bool
    strict_margin_m: float | None
    strict_binding_classification: str | None
    lenient_pass: bool
    lenient_margin_m: float | None
    lenient_binding_classification: str | None
    prohibited_outright: bool
    interpretations_disagree: bool


def evaluate_candidate(
    own_classification: str,
    zone_rules: dict,
    strict_distances: dict,
    lenient_distances: dict,
) -> EvaluationResult:
    """Evaluate one candidate address. own_classification is its own
    street's classification (alta/moderada/baja/sin_superacion).
    zone_rules is a ZpaeZone.rules dict. strict_distances and
    lenient_distances map classification -> nearest competitor distance
    in metres, or are missing/None for a classification with no
    competitor found within the search cutoff (meaning comfortably
    clear, not unknown)."""
    rule = zone_rules.get(own_classification)

    if rule is None:
        # This zone's plan doesn't regulate this classification at all.
        return EvaluationResult(
            strict_pass=True, strict_margin_m=None, strict_binding_classification=None,
            lenient_pass=True, lenient_margin_m=None, lenient_binding_classification=None,
            prohibited_outright=False, interpretations_disagree=False,
        )

    if rule.prohibited_outright:
        return EvaluationResult(
            strict_pass=False, strict_margin_m=None, strict_binding_classification=None,
            lenient_pass=False, lenient_margin_m=None, lenient_binding_classification=None,
            prohibited_outright=True, interpretations_disagree=False,
        )

    def _evaluate_one(distances: dict) -> tuple:
        if not rule.min_distance_m:
            return True, None, None
        margins = {}
        for classification, threshold in rule.min_distance_m.items():
            nearest = distances.get(classification)
            margins[classification] = float("inf") if nearest is None else (nearest - threshold)
        binding_classification = min(margins, key=margins.get)
        binding_margin = margins[binding_classification]
        passed = binding_margin >= 0
        reported_margin = None if binding_margin == float("inf") else binding_margin
        return passed, reported_margin, binding_classification

    strict_pass, strict_margin, strict_binding = _evaluate_one(strict_distances)
    lenient_pass, lenient_margin, lenient_binding = _evaluate_one(lenient_distances)

    return EvaluationResult(
        strict_pass=strict_pass, strict_margin_m=strict_margin,
        strict_binding_classification=strict_binding,
        lenient_pass=lenient_pass, lenient_margin_m=lenient_margin,
        lenient_binding_classification=lenient_binding,
        prohibited_outright=False,
        interpretations_disagree=(strict_pass != lenient_pass),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_distance_engine.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/distance_engine.py tests/test_distance_engine.py
git commit -m "$(cat <<'EOF'
Add rule-evaluation logic for the distance engine

evaluate_candidate applies a zone's ClassificationRule against
precomputed strict/lenient nearest-competitor distances, handling the
prohibited-outright short-circuit, per-classification margin
comparison (binding = smallest margin across all checked
classifications), and flagging when the two interpretations disagree.
Pure logic, no geopandas/cityseer dependency.
EOF
)"
```

---

### Task 4: Landuse-layer builders for the two interpretations

**Files:**
- Modify: `src/distance_engine.py`
- Modify: `tests/test_distance_engine.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `distance_engine.build_classification_landuse_gdf(competitors_gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame`, `distance_engine.build_lenient_competitor_points(competitors_gdf: geopandas.GeoDataFrame, nodes_gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame` — both used by Task 5's `scripts/08_compute_distances.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_distance_engine.py`:

```python
import geopandas as gpd
from shapely.geometry import Point

from distance_engine import build_classification_landuse_gdf, build_lenient_competitor_points


def test_build_classification_landuse_gdf_drops_unclassified():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta", None]},
        geometry=[Point(0, 0), Point(10, 10)],
        crs="EPSG:25830",
    )
    result = build_classification_landuse_gdf(competitors)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"


def test_build_lenient_competitor_points_uses_node_coordinates():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta"], "nearest_node_id": ["n1"]},
        geometry=[Point(5, 5)],  # real position, offset from the node
        crs="EPSG:25830",
    )
    nodes_gdf = gpd.GeoDataFrame(
        {"node_id": ["n1"]}, geometry=[Point(0, 0)], crs="EPSG:25830",
    )
    result = build_lenient_competitor_points(competitors, nodes_gdf)
    assert len(result) == 1
    assert result.iloc[0]["classification"] == "alta"
    assert result.iloc[0].geometry.x == 0.0
    assert result.iloc[0].geometry.y == 0.0


def test_build_lenient_competitor_points_drops_unclassified():
    competitors = gpd.GeoDataFrame(
        {"classification": ["alta", None], "nearest_node_id": ["n1", "n2"]},
        geometry=[Point(5, 5), Point(50, 50)],
        crs="EPSG:25830",
    )
    nodes_gdf = gpd.GeoDataFrame(
        {"node_id": ["n1", "n2"]}, geometry=[Point(0, 0), Point(40, 40)], crs="EPSG:25830",
    )
    result = build_lenient_competitor_points(competitors, nodes_gdf)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_distance_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_classification_landuse_gdf'`

- [ ] **Step 3: Implement the landuse-layer builders**

Append to `src/distance_engine.py`:

```python
import geopandas as gpd


def build_classification_landuse_gdf(competitors_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Filter to competitors with a known classification, ready to feed
    to cityseer's compute_accessibilities as the 'strict' landuse layer
    -- their own real positions, with each competitor's own offset from
    the network folded in automatically by cityseer's internal
    edge-assignment."""
    classified = competitors_gdf[competitors_gdf["classification"].notna()]
    return classified[["classification", "geometry"]].reset_index(drop=True)


def build_lenient_competitor_points(
    competitors_gdf: gpd.GeoDataFrame, nodes_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Build the 'lenient' landuse layer: synthetic points placed exactly
    at each classified competitor's already-snapped network node
    (offset zero by construction), for the network-distance-only
    interpretation. nodes_gdf must have 'node_id' and 'geometry'
    columns (see network.nodes_gdf_from_graph, Stage 3)."""
    classified = competitors_gdf[competitors_gdf["classification"].notna()]
    merged = classified.merge(
        nodes_gdf[["node_id", "geometry"]], left_on="nearest_node_id",
        right_on="node_id", suffixes=("", "_node"),
    )
    return gpd.GeoDataFrame(
        {"classification": merged["classification"].values},
        geometry=merged["geometry_node"].values,
        crs=competitors_gdf.crs,
    )
```

Note: place the `import geopandas as gpd` at the top of `src/distance_engine.py` alongside the existing `from dataclasses import dataclass` line, not repeated inline — this file now has both pure-Python and geopandas-dependent functions in it, which is fine (it stays one file per the plan's file structure), just keep the imports at the top as usual.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_distance_engine.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/distance_engine.py tests/test_distance_engine.py
git commit -m "$(cat <<'EOF'
Add landuse-layer builders for strict/lenient interpretations

build_classification_landuse_gdf filters competitors to the
classified subset for the strict pass (real positions, cityseer
handles their offset). build_lenient_competitor_points builds
synthetic zero-offset points at each competitor's already-snapped
network node for the lenient pass.
EOF
)"
```

---

### Task 5: Distance computation and evaluation script

**Files:**
- Create: `scripts/08_compute_distances.py`

**Interfaces:**
- Consumes: `distance_engine.build_classification_landuse_gdf`, `distance_engine.build_lenient_competitor_points`, `distance_engine.evaluate_candidate` (Tasks 3-4), `network.nodes_gdf_from_graph` (Stage 3), `zones.ZONES` (Stage 1).
- Produces: `data/processed/distance_evaluation_results.gpkg`.

This is the pipeline's most complex orchestration script — it makes real cityseer calls whose exact behavior was verified via smoke tests before this plan was written, but the FULL real-scale run (32,076-node decomposed graph, ~3,900 classified competitors, ~9,800 evaluable candidates) has not been executed yet. No new unit tests (real-library orchestration, consistent with prior stages) — verification is a live run with careful judgment on the output, not just "did it crash."

- [ ] **Step 1: Write the script**

Create `scripts/08_compute_distances.py`:

```python
"""
Stage 4: compute network distance from every candidate address to the
nearest relevant competitor (per classification), under both the strict
(door-to-door, offsets included) and lenient (network-distance-only)
interpretations, and evaluate each against its zone's threshold rule.

Run locally (after scripts/07_tag_zones_and_classifications.py has
produced its output):
    python scripts/08_compute_distances.py
"""

import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cityseer.metrics.layers as layers
import cityseer.tools.io as cs_io
import geopandas as gpd
import pandas as pd

from distance_engine import (
    build_classification_landuse_gdf,
    build_lenient_competitor_points,
    evaluate_candidate,
)
from network import nodes_gdf_from_graph
from zones import ZONES

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CRS = "EPSG:25830"
# Safely above the largest real threshold in scope (300m, Centro's
# baja-vs-alta) so "not found within this cutoff" always means "clearly
# passes," never "unknown."
SEARCH_CUTOFF_M = 350
CLASSIFICATION_KEYS = ["alta", "moderada", "baja", "sin_superacion"]

ZONE_BY_NAME = {zone.name: zone for zone in ZONES}

with open(PROCESSED_DIR / "network_graph_zpae.pickle", "rb") as f:
    graph = pickle.load(f)

nodes_gdf, edges_gdf, net_struct = cs_io.network_structure_from_nx(graph)
print(f"Network: {len(nodes_gdf)} nodes.")

candidates = gpd.read_file(PROCESSED_DIR / "candidate_addresses_zpae_tagged.gpkg")
competitors = gpd.read_file(PROCESSED_DIR / "hosteleria_competitors_zpae_tagged.gpkg")

# --- Strict pass: competitors' real positions (cityseer folds their own
# offset in automatically via edge-assignment) ---
strict_landuse = build_classification_landuse_gdf(competitors)
print(f"Strict landuse layer: {len(strict_landuse)} classified competitors.")
strict_nodes, _ = layers.compute_accessibilities(
    data_gdf=strict_landuse,
    landuse_column_label="classification",
    accessibility_keys=CLASSIFICATION_KEYS,
    nodes_gdf=nodes_gdf,
    network_structure=net_struct,
    distances=[SEARCH_CUTOFF_M],
)

# --- Lenient pass: synthetic competitor points at their own snapped node
# (offset zero by construction) ---
graph_nodes_gdf = nodes_gdf_from_graph(graph, crs=CRS)
lenient_landuse = build_lenient_competitor_points(competitors, graph_nodes_gdf)
print(f"Lenient landuse layer: {len(lenient_landuse)} classified competitors.")
lenient_nodes, _ = layers.compute_accessibilities(
    data_gdf=lenient_landuse,
    landuse_column_label="classification",
    accessibility_keys=CLASSIFICATION_KEYS,
    nodes_gdf=nodes_gdf,
    network_structure=net_struct,
    distances=[SEARCH_CUTOFF_M],
)


def _distances_at_node(nodes_result: gpd.GeoDataFrame, node_id: str) -> dict:
    if node_id not in nodes_result.index:
        return {}
    row = nodes_result.loc[node_id]
    result = {}
    for key in CLASSIFICATION_KEYS:
        col = f"cc_{key}_nearest_max_{SEARCH_CUTOFF_M}"
        value = row[col]
        result[key] = None if pd.isna(value) else float(value)
    return result


evaluable = candidates[candidates["zpae_zone"].notna() & candidates["classification"].notna()]
print(f"Candidates to evaluate: {len(evaluable)} / {len(candidates)} "
      f"(inside a zone AND matched to a classified street).")

results = []
for _, row in evaluable.iterrows():
    zone = ZONE_BY_NAME[row["zpae_zone"]]
    node_id = row["nearest_node_id"]

    strict_distances = _distances_at_node(strict_nodes, node_id)
    strict_distances = {
        k: (v + row["offset_distance_m"] if v is not None else None)
        for k, v in strict_distances.items()
    }
    lenient_distances = _distances_at_node(lenient_nodes, node_id)

    evaluation = evaluate_candidate(
        own_classification=row["classification"],
        zone_rules=zone.rules,
        strict_distances=strict_distances,
        lenient_distances=lenient_distances,
    )
    results.append({
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
    })

results_gdf = gpd.GeoDataFrame(results, geometry="geometry", crs=CRS)
print(f"\nResults: {int(results_gdf['strict_pass'].sum())} pass (strict), "
      f"{int((~results_gdf['strict_pass']).sum())} fail (strict).")
print(f"Results: {int(results_gdf['lenient_pass'].sum())} pass (lenient), "
      f"{int((~results_gdf['lenient_pass']).sum())} fail (lenient).")
print(f"Disagreements between interpretations: "
      f"{int(results_gdf['interpretations_disagree'].sum())}")
print(f"Outright-prohibited (Alta zones): "
      f"{int(results_gdf['prohibited_outright'].sum())}")

out_path = PROCESSED_DIR / "distance_evaluation_results.gpkg"
results_gdf.to_file(out_path, driver="GPKG")
print(f"Saved to {out_path}")
```

- [ ] **Step 2: Run it against the real data**

Run: `source .venv/bin/activate && python scripts/08_compute_distances.py`

This is the first full-scale run of this exact call sequence — verify the following carefully, not just "did it crash":

1. **Column names**: the script assumes `compute_accessibilities` produces columns named `cc_{key}_nearest_max_{SEARCH_CUTOFF_M}` for each of the four classification keys (confirmed pattern from a 2-key smoke test during design; verify it holds for all 4 keys and prints without a `KeyError`). If `_distances_at_node` raises a `KeyError`, print `strict_nodes.columns.tolist()` and compare against what's expected — do not guess a fix, look at the real column names returned.
2. **Node-id matching**: the script assumes `nodes_gdf`'s index (from `network_structure_from_nx`) uses the same string keys (`"x123.4-y456.7"` format) as `nearest_node_id` values stored in the Stage 3 snapped files. If most/all `_distances_at_node` calls return `{}` (node_id not found), this assumption is wrong — investigate before proceeding, don't silently accept empty results as "no competitors nearby."
3. **Evaluable candidate count**: should be close to 9,838 (verified against real data before this plan was written — see Task 2's expected output). A wildly different number signals something upstream changed or this script is filtering incorrectly.
4. **Pass/fail sanity**: a very high fail rate (most candidates failing) or a very low one (nearly all passing) in a ZPAE zone specifically created because hostelería density is already excessive would both be worth a second look — these zones exist because they're saturated, so a meaningful fail rate is expected, but "100% fail" or "0% fail" would both be suspicious given four zones with different degrees of restriction (recall AZCA has no Alta chapter at all).
5. Both output columns' pass counts, disagreement count, and outright-prohibited count are printed — sanity-check the outright-prohibited count against a rough expectation: candidates classified `alta` in Centro/Gaztambide/Trafalgar (all of which ban Alta outright) should ALL show `prohibited_outright=True`; AZCA has no Alta chapter so contributes zero to this count regardless of any AZCA candidate's classification.
6. `data/processed/distance_evaluation_results.gpkg` exists after the run.

If any of these checks reveal a real problem (not just numbers slightly different from the estimate due to floating-point/version differences), stop and investigate rather than reporting DONE — this script's correctness is the actual point of Stage 4, more than any prior script's.

- [ ] **Step 3: Commit**

```bash
git add scripts/08_compute_distances.py
git commit -m "$(cat <<'EOF'
Add distance computation and rule evaluation script

Runs two cityseer compute_accessibilities passes (strict: real
competitor positions with their offset folded in automatically;
lenient: synthetic zero-offset points at competitors' snapped nodes),
then evaluates every candidate that's both inside a zone and matched
to a classified street against its zone's threshold rule.
EOF
)"
```

---

## Post-plan verification

After Task 5, run the full test suite once more to confirm nothing regressed:

Run: `source .venv/bin/activate && pytest -v`
Expected: all tests across every `tests/test_*.py` file pass (44 tests total: 31 from Stages 1-3 + 6 from Task 1 + 8 from Tasks 3-4).
