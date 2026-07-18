# Stage 3: Cityseer-compatible network graph + point snapping

## Purpose

Stage 1 established the distance-threshold rules and clipped the raw street
network to the four ZPAE zones. Stage 2 built the competitor point layer and
candidate-address context. Stage 3 turns the raw clipped street segments into
an actual walkable network graph, ready for Stage 4 to compute real
network distances over.

## Non-goals for this stage

- Any shortest-path / network-distance computation — that's Stage 4.
- Any pass/fail threshold evaluation — that's Stage 4.
- Re-deriving the ZPAE zone or competitor/candidate data — both already exist
  from Stages 1–2 and are consumed as-is.

## Ground truth findings (2026-07-18)

Confirmed against the real clipped data (`data/processed/
rt_tramo_vial_zpae_clip.gpkg`, 4,380 segments) before finalizing this design:

- **The node-to-segment relation table the original docs assumed
  (`rrt_nodoctra_tramo`) does not exist in this download.** Only a standalone
  `rt_nodoctra_p` nodes layer and the raw segments themselves are present —
  no pre-built topology to rely on. The graph must be built directly from
  segment geometry (endpoint-coordinate matching), the same approach used for
  OSM-based Cityseer graphs generally, not a project-specific workaround.
- **`situacion` (underground/surface/elevated) matters more than the vehicle-
  access tag for walkability.** 66 segments are tagged `Subterráneo`
  (underground) and most are still tagged pedestrian-accessible
  (`Peatón+bici+vehículo`) — but manual inspection confirms these are real
  Madrid car tunnels (Princesa, Bailén, San Vicente, the A-5/A-6/M-30 ring),
  not places pedestrians actually walk; Madrid pedestrians use surface
  crossings instead. The 10 `Elevado` (elevated) segments, by contrast,
  include real pedestrian viaducts (e.g. Segovia) and are kept.
- **`tipovehic`/`clase` still matter as an independent filter.** 36 segments
  are `Solo vehículo` (vehicle-only) and 36 are `Autopista libre/autovía`
  (motorway class) — these are the same physical segments (A-5, A-6, Calle
  30/M-30) and were never pedestrian routes regardless of the tunnel
  question above.
- **`titular` (owner) is a no-op filter within our clip** — all 4,380
  segments are already `Ayuntamiento` (5), so Stage 1's zone clip already
  implicitly selected municipal streets; no further filtering needed there.
- **`sentido` (one-way/two-way) is a vehicle-routing attribute, not a
  pedestrian one.** The Normativa's own text measures distance "door to
  door along the axis of streets," not vehicle routing — pedestrians walk
  both directions on a one-way street. The graph is undirected regardless
  of `sentido`.
- **`rt_tramo_vial` has duplicate `id_tramo` rows by design** — the layer is
  itself a join of segments to street names (`rt_tramo_l` × `rt_vial_a`), so
  a segment shared by two named streets (a corner, or a bike path overlapping
  a named street) appears as two identical-geometry rows under the same
  `id_tramo` (confirmed: 8 such pairs in our clip, e.g. a segment tagged
  both "DOCTOR FOURQUET" and "ARGUMOSA"). Must dedupe by `id_tramo` before
  building topology, or the graph would double-count these edges.

## Design decisions

1. **Filter to a walkable network**: drop `situacion == 'Subterráneo'`
   (underground/tunnels — value `2`), `tipovehic == '001 '` (vehicle-only),
   and `clase == 1002` (motorway). Keep everything else, including elevated
   segments and the two "Vial bici" (bike path) segments (shared-use
   assumption, immaterial at n=2 either way).
2. **Dedupe by `id_tramo`** before building topology — keep the first
   occurrence; the street-name attribute isn't used downstream at this
   stage, so which duplicate survives doesn't matter functionally.
3. **Build topology from geometry**, not from any relation table: each
   segment's first/last coordinate becomes a graph node (matched by
   coincident coordinates across segments), each segment becomes an edge
   between its two endpoint nodes. This matches how the IGR-RT model already
   segments streets at intersections (`tipo_tramo` includes an explicit
   "Nudo" junction type), so no mid-segment splitting is needed.
4. **Undirected graph** — ignore `sentido` entirely (see ground truth above).
5. **Connectivity validation on the base (pre-decomposition) graph** — report
   connected-component count and sizes. A disconnected pocket within a ZPAE
   zone would silently break Stage 4's shortest-path calculations for any
   address caught in it; this must be surfaced, not discovered later.
6. **Decompose at 10m via Cityseer's `nx_decompose`** after connectivity
   validation, before snapping. Rationale (discussed and confirmed): 10m
   decomposition gives a ~5m worst-case node-snapping offset, which is
   ~17% of the tightest real threshold in scope (AZCA's 30m baja-to-baja) —
   tight enough given that other error sources in this pipeline (candidate
   address geocoding precision, exact door position along a building
   frontage) are already likely larger than that. 5m decomposition was
   considered and rejected: it roughly doubles graph size for an accuracy
   gain smaller than those other error sources. The exact `nx_decompose`
   call signature/parameters will be confirmed against whatever Cityseer
   version gets installed — verify against the real library, don't assume
   the API from memory (same discipline as Stages 1–2's live-API work).
7. **Snap-to-nearest-node, not nearest-edge**: simpler, and made
   sufficiently accurate by the 10m decomposition (nodes now exist roughly
   every 10m along every street, not just at intersections). Record the
   `offset_distance_m` for every snapped point so Stage 4 can add it back
   into the final network-distance calculation (point→node + node→node +
   node→point), rather than silently dropping that precision.

## Pipeline

Two scripts, continuing the existing numbered convention, backed by a new
`src/network.py` module holding the testable pure logic — same split as
Stage 2's fetch/reconcile scripts + `src/hosteleria.py`.

### `scripts/05_build_network_graph.py`

1. Load `data/processed/rt_tramo_vial_zpae_clip.gpkg`.
2. Apply the walkability filter (decision 1).
3. Dedupe by `id_tramo` (decision 2).
4. Build an undirected `networkx` graph from segment geometry (decisions 3–4):
   nodes keyed by coordinate, edges carrying `length_m` and the segment's
   original attributes (`id_tramo`, `nombre`, etc.) for traceability.
5. Report connectivity: number of connected components, size of each,
   flagged loudly if more than one component exists within a single zone's
   footprint (decision 5).
6. Convert to Cityseer's network structure and decompose at 10m
   (decision 6).
7. Save the decomposed graph to `data/processed/network_graph_zpae.<ext>`
   (exact format TBD in the implementation plan — whichever format
   round-trips cleanly through Cityseer's own I/O, confirmed against the
   real library rather than assumed).

### `scripts/06_snap_points_to_network.py`

1. Load the Stage 3 decomposed graph and Stage 2's two point layers
   (`hosteleria_competitors_zpae_clip.gpkg`,
   `candidate_addresses_zpae_clip.gpkg`).
2. For each point in both layers, snap to the nearest graph node and record
   `nearest_node_id` + `offset_distance_m` (decision 7).
3. Save both layers, augmented with those two columns, to
   `data/processed/hosteleria_competitors_snapped.gpkg` and
   `data/processed/candidate_addresses_snapped.gpkg`.

## Testing approach

- **Pure logic in `src/network.py`** (filter predicate, `id_tramo` dedup,
  endpoint-coordinate topology builder) gets unit tests with small synthetic
  GeoDataFrames — same pattern as Stage 2's `src/hosteleria.py` tests, no
  real data or real Cityseer calls required.
- **Cityseer conversion, decomposition, and snapping** depend on the real
  library and real data shape (this is exactly where Stage 1/2's "verify the
  live API, don't assume the docs" lesson applies to a third-party library
  instead of a data source). These get verified by running the scripts
  against the real clipped data and inspecting the printed connectivity and
  offset-distance reports, not by mocked unit tests.

## Open questions / deferred decisions

- Exact save format for the decomposed graph — will be resolved during
  implementation by checking what Cityseer's own I/O utilities actually
  support cleanly in the installed version.
- If the connectivity check finds more than one component within a zone,
  that's a real finding to bring back for a decision (route around it,
  investigate the data gap, or accept isolated addresses as unreachable) —
  not something to silently paper over during implementation.
