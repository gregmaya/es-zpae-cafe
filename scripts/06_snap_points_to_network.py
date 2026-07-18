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
