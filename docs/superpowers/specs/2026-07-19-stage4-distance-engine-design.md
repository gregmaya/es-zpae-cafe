# Stage 4: Distance engine

## Purpose

Stages 1–3 built the rule (`src/zones.py`), the competitor/candidate point
layers (Stage 2), and the walkable network graph with both point layers
snapped onto it (Stage 3). Stage 4 computes the actual network distance
from every candidate address to the nearest relevant competitor, evaluates
it against the applicable threshold rule, and produces a pass/fail result
with margin in metres per candidate.

## Non-goals for this stage

- Precomputing/baking results for every address at scale, or any output
  format meant for the web app — that's Stage 5.
- Any web/UI work — Stage 6.
- Re-deriving the rule, the point layers, or the network graph — all three
  already exist from Stages 1–3 and are consumed as-is.

## Ground truth findings (2026-07-18/19)

Confirmed before finalizing this design, not assumed:

- **Neither the candidate nor competitor point layers carry ZPAE zone or
  street-classification tags yet.** Checked directly:
  `candidate_addresses_zpae_snapped.gpkg` has columns `id_porpk`,
  `has_commercial_local`, `current_activity_summary`,
  `is_existing_hosteleria_class`, `nearest_node_id`, `offset_distance_m`,
  `geometry` — no zone or classification field.
  `hosteleria_competitors_zpae_snapped.gpkg` has `id_local`, `rotulo`,
  `decreto_class`, `desc_epigrafe`, `nearest_node_id`, `offset_distance_m`,
  `geometry` — same gap. This tagging step was never done in Stages 1–3
  and has to happen before any threshold evaluation, since the rule's
  `min_distance_m` is keyed by classification.
- **`cityseer.metrics.layers.compute_accessibilities` is the right tool for
  the core distance computation**, confirmed via a live smoke test on
  synthetic data (2026-07-19): given a "landuse" point layer with a
  category column, it computes, for every node in the network in one pass,
  a count and the nearest-distance to each category within a given
  distance cutoff. This avoids an all-pairs comparison (~5,341 competitors
  × ~13,876 candidates ≈ 74 million pairs, clearly infeasible) — the
  computation runs once per node (~32,000 nodes) instead. Confirmed
  real network distance (not straight-line) via the smoke test's numbers.
  Returned node columns follow the pattern `cc_{key}_nearest_max_{distance}`
  (nearest distance to category `key`, cutoff at `distance` metres) —
  verified directly on the installed cityseer 5.6.1, not assumed from the
  docstring (which itself has known discrepancies from actual behavior in
  this library, e.g. `nx_consolidate_nodes`'s default value being wrong in
  its own docstring text, found during Stage 3).
- **`compute_accessibilities` already accounts for a competitor's own
  precise position relative to the network** — its internal data-to-network
  assignment computes distance via the exact nearest point on the nearest
  street edge, not via a coarser nearest-existing-node approximation.
  Confirmed with a hand-checked synthetic case (a point 5m along one axis
  and 2m perpendicular from a node reported exactly 7.0m network distance
  — the 5m-along-edge + 2m-perpendicular sum, not a straight-line 5.39m).
  This means the "strict" interpretation (see below) doesn't need any
  extra plumbing for the competitor side — only the candidate side needs
  its Stage-3 offset added on top, since `compute_accessibilities`
  aggregates results at nodes, not at arbitrary candidate points.
- **A lower-level primitive (`cityseer.metrics.layers.build_data_map`,
  returning a Rust `DataMap`) was investigated as a way to get symmetric
  edge-precision for candidates too, and abandoned.** Its `DataEntry`
  objects don't expose the assignment distance/node as simple Python
  attributes (only `data_key`, `geom_wkt`), and the higher-level
  `compute_accessibilities` docstring's promised `nearest_assigned`/
  `next_nearest_assign` output columns did not appear in the actual
  returned `data_gdf` in the same 5.6.1 smoke test — a third
  docstring-vs-behavior mismatch found in this library (after Stage 3's
  two). Chasing this further wasn't worth it: see the interpretation
  discussion below for why candidate-side precision doesn't need to match
  competitor-side precision exactly.

## Design decisions

### 1. Zone + classification tagging (new work, folded into this stage)

For every candidate and competitor point:
- **Zone membership**: point-in-polygon test against `zpae_ambitos.geojson`
  (the four zone boundary polygons from Stage 1). A point outside all four
  polygons is tagged "not regulated" and excluded from threshold
  evaluation entirely — this matches the project's own stated non-goal
  ("no coverage outside the four declared ZPAE polygons... no distance
  restriction applies at all under this rule"). Necessary because Stage
  1/2's clips used a 300m buffer *beyond* the zone boundaries for network
  connectivity, so plenty of candidate addresses in that buffer margin are
  geographically close to a zone but legally outside it.
- **Street classification**: nearest-line match against
  `zpae_clasificacion.geojson` (the per-street-segment alta/moderada/baja/
  sin-superación layer from Stage 1). This one join gives both the zone
  name and the classification together, since `zpae_clasificacion.geojson`
  carries both — no need for a second lookup once the nearest line is
  found. (Recall from Stage 1: the zone-name spelling differs between
  `zpae_ambitos.geojson` and `zpae_clasificacion.geojson` — don't join on
  the zone-name text field directly; `src/zones.py`'s `ZpaeZone.name` /
  `ZpaeZone.clasificacion_name` fields already record both spellings for
  exactly this reason.)

### 2. Cross-zone competitors count (confirmed interpretive decision, not a default)

The four zones sit close together in central Madrid (Centro borders
Chamberí's two zones). Whether a competitor in a *different* zone than the
candidate should count toward that candidate's distance check is
genuinely ambiguous in the text: each zone's Normativa refers to
"actividades ... que estén en zonas de contaminación acústica alta" as a
term defined within that zone's own chapter (e.g. Trafalgar's Capítulo II
"Zonas de Contaminación Acústica Alta"), which could be read either as
scoped to that zone's own delimited ambit, or as a general acoustic
classification that happens to be measured the same way across zones.
**Decision (confirmed with the project owner, 2026-07-19): cross-zone
competitors DO count.** A candidate's own zone determines which rule
(`ClassificationRule.min_distance_m`) applies, but the competitor search
is not restricted to that same zone — any competitor within range,
classified by its own street regardless of which zone it belongs to, is
considered. This is a deliberate, documented interpretive choice, not an
oversight — a future reader who disagrees with it should be able to find
this paragraph and the reasoning behind it.

Practically, this simplifies the computation: competitors are grouped
into four classification categories *globally* (not per-zone) for the
accessibility computation in Decision 3, since `src/zones.py`'s
`min_distance_m` dicts are already keyed by classification label alone,
not by "zone X's alta" specifically.

### 3. Dual distance interpretation: strict vs. lenient (confirmed decision)

The Normativa text measures distance "desde la puerta del local existente
a la del que pretende instalarse" (door to door) — the door is explicitly
named as the endpoint, which argues for including the walk from door to
street axis in the total. But this project's own Stage 3 work already
found that raw offset distances are sometimes large (up to ~113–117m) and
dominated by genuine geocoding-to-centerline distance (building setback,
plaza addresses), not by any error in the network or snapping — meaning
"include the offset" and "don't include the offset" can produce
meaningfully different answers for some addresses, and the correct
reading is genuinely disputable.

**Decision: compute and report both**, rather than silently picking one:
- **Strict** (offset included): network distance between snapped nodes,
  computed via `compute_accessibilities` using competitors' *real*
  positions (their own offset is folded in automatically, per the ground
  truth finding above), plus the candidate's own Stage-3
  `offset_distance_m` added on top.
- **Lenient** (offset ignored): network distance only. Computed via a
  *second* `compute_accessibilities` pass using synthetic competitor
  points placed exactly at their Stage-3 `nearest_node_id` coordinates
  (offset zero by construction), and the candidate's own node-level
  result is used directly with no offset added.

Both interpretations are computed at the *same* underlying network
distances — the only difference is which side's offset gets added, so
this is not a second, independent pipeline, just two additive treatments
of numbers that mostly already exist. Where the two interpretations agree
(most cases, given offsets are small relative to typical thresholds),
the result is unambiguous. Where they disagree — pass under one, fail
under the other — that is flagged explicitly as a borderline case, not
resolved by picking a side.

### 4. Rule evaluation

Per candidate address, using its assigned zone (Decision 1) and
`src/zones.py`'s `ZONES` list:
1. Look up the `ClassificationRule` for the candidate's own street
   classification within its zone.
2. If `prohibited_outright`, the result is FAIL under both
   interpretations, no distance computation needed for this candidate.
3. Otherwise, for each classification key present in that rule's
   `min_distance_m` dict, compare the nearest same-classification
   competitor's distance (strict and lenient, Decision 3) against the
   threshold. The candidate FAILS if *any* classification's nearest
   competitor is closer than that classification's threshold, under
   either interpretation being evaluated. Margin is reported as the
   smallest (threshold − distance) across all classifications checked —
   the binding constraint.
4. `prohibited_with_music` is not evaluated — this project models plain
   hostelería (café/bar) only, per its stated scope; the music-venue
   carve-out doesn't apply to what this tool checks.

## Pipeline

Continuing the established fetch/reconcile-style split, backed by testable
pure logic in `src/distance_engine.py`.

### Zone + classification tagging script

Loads candidate and competitor point layers (Stage 3 outputs) plus
`zpae_ambitos.geojson` and `zpae_clasificacion.geojson` (Stage 1 outputs).
Applies point-in-polygon (zone) and nearest-line (classification) joins.
Saves both point layers augmented with `zpae_zone` and `classification`
columns (or a "not regulated" marker for out-of-zone candidates).

### Distance computation + evaluation script

Loads the tagged point layers and the Stage 3 network graph. Runs the two
`compute_accessibilities` passes (Decision 3). For each candidate not
tagged "not regulated," evaluates the rule (Decision 4) using
`src/zones.py`'s `ZONES`. Saves a results table: one row per candidate,
with strict/lenient distances per relevant classification, strict/lenient
pass-fail, strict/lenient margin, and a `interpretations_disagree` flag.

## Testing approach

- **Pure logic in `src/distance_engine.py`** (rule evaluation given
  precomputed distances, margin calculation, the
  prohibited-outright short-circuit, the disagreement flag) gets unit
  tests with synthetic inputs — no real network or cityseer calls needed
  to test this part, same pattern as prior stages' pure-logic modules.
- **Zone/classification tagging and the `compute_accessibilities` calls**
  depend on real data shape and the real library's actual (not
  docstring-assumed) behavior — verified by running against the real
  Stage 1–3 outputs and inspecting the results, same "ground truth via
  real run" discipline as every prior stage.

## Open questions / deferred decisions

- Exact column-naming scheme for the results table — resolved during
  implementation.
- Whether `is_existing_hosteleria_class` (from Stage 2's candidate
  context) should influence how a candidate's own result is interpreted
  or displayed (e.g. "this address already has a hostelería — you'd be
  evaluating a modification, not a new opening") — out of scope for the
  distance *computation* itself, but worth revisiting when Stage 6's web
  app decides how to present results.
- The `n_nearest_candidates` and `max_netw_assign_dist` parameters on
  `compute_accessibilities` (defaults 50 and 100.0m respectively, per the
  verified signature) were not tuned during this design — the default
  100m assignment distance is comfortably larger than any offset we've
  seen in this dataset, but should be sanity-checked against the real
  full-scale run during implementation, not assumed safe from the smoke
  test alone.
