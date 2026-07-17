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
