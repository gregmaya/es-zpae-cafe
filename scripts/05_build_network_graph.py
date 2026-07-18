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
# design doc). nx_consolidate_nodes then merges near-coincident junction
# nodes. nx_remove_filler_nodes then merges degree-2 nodes (intermediate
# points that aren't real junctions) into single edges, retaining the merged
# edge's full path geometry.
base_graph = cs_io.nx_from_generic_geopandas(deduped)

# Task 2 (see .superpowers/sdd/task-2-report.md) found the raw graph split
# into 27 connected components: one dominant component (2,581 nodes,
# 97.9%) plus 26 tiny orphans (24 of size 2, 2 of size 4). Root cause:
# sub-metre coordinate-precision mismatches in the source IGR-RT geometry
# -- two segments that should share an exact junction node have endpoints
# differing by a tiny epsilon, so cityseer's exact-coordinate node-matching
# treats them as separate, disconnected nodes (not a clipping-boundary
# artifact -- orphan points sit 60-422m inside the study-area buffer, some
# inside the ZPAE Centro zone itself). nx_consolidate_nodes merges nodes
# within buffer_dist of each other, closing these gaps. We deliberately
# override the library default (buffer_dist=12, tuned for OSM-style
# intersection cleanup) with a conservative buffer_dist=2: large enough to
# close sub-metre digitization gaps, small enough that it won't merge
# genuinely distinct junctions, which are almost always well over 2m apart
# even in the densest parts of central Madrid. Run this before filler-node
# removal / decomposition so it targets the original junction-precision
# issue directly, rather than an already-simplified/subdivided graph.
base_graph = graphs.nx_consolidate_nodes(base_graph, buffer_dist=2)

base_graph = graphs.nx_remove_filler_nodes(base_graph)
print(f"Base graph: {base_graph.number_of_nodes()} nodes, "
      f"{base_graph.number_of_edges()} edges.")

components = list(nx.connected_components(base_graph))
print(f"Connected components: {len(components)}")
# After consolidation, 4 size-2 orphan pairs remain (8 of ~32,000 nodes in
# the final decomposed graph). This was investigated: increasing buffer_dist
# from 2m to 3m yielded no further improvement, ruling out simple precision
# gaps. The residual is accepted as a known limitation (likely elevated/
# pedestrian-bridge segments whose endpoints don't align with the surface
# network). Stage 4 should flag any candidate/competitor point snapping to
# these orphan nodes as unreachable, rather than re-deriving this finding.
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
