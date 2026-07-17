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
