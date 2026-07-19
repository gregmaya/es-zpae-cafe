# Nearest-competitor identity — design

## Purpose

Stage 4 (`08_compute_distances.py` / `src/distance_engine.py`) already computes,
per candidate address, the nearest network distance to a classified competitor
for each street-classification (alta/moderada/baja/sin_superacion), under both
the strict (door-to-door, offsets included) and lenient (network-distance-only)
interpretations. That's enough to decide pass/fail, but it throws away *which*
competitor produced each distance.

For the eventual UI, we want to be able to say "this address fails because
it's 42m from Bar X (a BAR SIN COCINA on a moderada street)" — not just "42m
from the nearest moderada-classification thing." This design adds that
identity lookup alongside the existing evaluation, without changing it.

## Scope confirmation

"Competitor" here means exactly the existing Stage 2 competitor layer: the
Decreto 184/1998 hostelería/ocio classes (`src/activities.py`) — restaurants,
bar-restaurants, bars, cafeterías, tabernas, bodegas, discotecas y salas de
baile, salas de fiesta (with/without food), bares especiales (with/without
actuaciones), cafés-espectáculo, and banquet halls. Gyms, pools, theatres,
museums, and accommodation are correctly out of scope — Stage 1 confirmed
they aren't gated by this rule at all. No new data sourcing is needed; this
is purely a new identity lookup over data that already exists.

## What gets computed

For every candidate address already in the `evaluable` set in
`08_compute_distances.py` (has a zpae_zone and a classification — unchanged,
this already includes prohibited-outright candidates), compute four
nearest-competitor lookups:

1. **strict, nearest of `strict_binding_classification`** — the specific
   competitor that determines the strict pass/fail margin already computed by
   `evaluate_candidate`. Null if the binding classification is `None` (rule
   doesn't gate this street's classification at all, or prohibited outright).
2. **lenient, nearest of `lenient_binding_classification`** — same, lenient
   interpretation.
3. **strict, nearest of any classification** — the single closest classified
   competitor regardless of classification (a "what's physically closest"
   context fact), strict interpretation.
4. **lenient, nearest of any classification** — same, lenient interpretation.

Each lookup, when found, reports: `id_local`, `rotulo` (name), `desc_epigrafe`
(activity type), `classification`, `distance_m`, and `x`/`y` (EPSG:25830,
plain float columns rather than a second geometry column, since GPKG layers
want one active geometry column — the candidate's own point stays as the
layer geometry).

Null (not "unknown") when no competitor is found within the existing 350m
`SEARCH_CUTOFF_M` — consistent with the existing convention that "not found
within cutoff" means comfortably clear, not indeterminate.

## Architecture

New module: `src/nearest_competitor.py`. Single responsibility: given a
candidate's network node, the walkable graph, and an index of competitors by
node, find the nearest one (optionally filtered to a classification).

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

def build_competitor_node_index(competitors_gdf) -> dict[str, list[dict]]:
    """Group competitors by nearest_node_id. Each competitor record carries
    id_local, rotulo, desc_epigrafe, classification, offset_distance_m, x, y."""

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
    """Bounded Dijkstra from node_id (networkx.single_source_dijkstra_path_length,
    cutoff=cutoff_m, weight='length'). For every reachable node with at least
    one competitor attached (optionally filtered by classification), compute
    each competitor's total distance: network distance alone if not strict,
    or network distance + candidate_offset_m + that competitor's own
    offset_distance_m if strict. Returns the minimum, ties broken by lowest
    id_local. None if nothing found within cutoff_m."""
```

One Dijkstra run per candidate node covers both interpretations (the
underlying network distances are identical; only the offset addition
differs), so this doesn't meaningfully add to Stage 4's runtime — it reuses
the same walkable graph pickle Stage 3 already produced, and runs alongside
(not instead of) the existing cityseer-based `evaluate_candidate` call, so
the already-validated pass/fail numbers are untouched.

## Integration into `08_compute_distances.py`

After computing `evaluation` for each row in `evaluable` (unchanged loop),
call `find_nearest_competitor` four times (strict/lenient ×
binding/overall) and append the results as new columns on the output row.
`competitor_index` is built once, before the loop, from the same `competitors`
gdf already loaded.

## Output schema

28 new columns on `distance_evaluation_results.gpkg`, four groups of seven:

```
strict_nearest_binding_{id_local,rotulo,desc_epigrafe,classification,distance_m,x,y}
lenient_nearest_binding_{...}
strict_nearest_overall_{...}
lenient_nearest_overall_{...}
```

All null together when no competitor is found within cutoff, or when the
relevant binding classification is `None` (binding-classification columns
only).

## Testing

Unit tests for `src/nearest_competitor.py` against a small synthetic graph
(a handful of nodes and edges with known lengths) and a couple of synthetic
competitor records with known offsets, covering:

- Correct nearest competitor picked by network distance.
- Classification filtering excludes non-matching competitors.
- Strict distance = network distance + candidate offset + competitor's own
  offset; lenient distance = network distance alone.
- Cutoff respected: a competitor just beyond cutoff_m returns `None`, not the
  next-nearest.
- Deterministic tie-break (lowest id_local) when two competitors are
  equidistant.
- `None` classification_filter falls back to nearest-of-any behavior.
