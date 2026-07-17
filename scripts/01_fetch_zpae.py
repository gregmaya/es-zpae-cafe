"""
Stage 1: pull the ZPAE zone boundaries and per-street classification.

The ArcGIS REST feature query endpoint (sigma.madrid.es MapServer layers
0-4) advertises polygon geometry but returns geometry=null on every feature
for every query variant tried (outSR on/off, spatial filter, geojson/json/
pbf, browser user-agent) -- attributes come back fine, geometry never does.
returnExtentOnly confirms real geometry exists server-side, so this looks
like a server-side bug/misconfiguration on the hosted layer, not a client
issue. Do not spend more time working around it here.

Use the direct shapefile download from the Ayuntamiento's Geoportal
instead, which has real geometry:
    https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/MEDIO_AMBIENTE/INFORMACION_ACUSTICA/ZPAE/ZPAE.zip

That zip contains two shapefiles with a materially different data model
than docs/data_sources.md originally assumed:
  - ZPAE.shp            4 polygons, one per zone (the "ambito"/boundary).
                         Fields: ZPAE, Id. No classification, no threshold.
  - ZPAE_clasificacion.shp   3241 LINE segments (not polygons) -- the
                         alta/moderada/baja/sin-superacion classification
                         is a per-STREET-SEGMENT attribute, not a per-area
                         one. Fields: ZPAE, Clasifica, Enlace, Observa.
                         This actually matches the project's premise
                         directly (threshold varies per street) and should
                         make joining to the IGR-RT network more natural
                         later.

Neither shapefile carries a numeric metre threshold anywhere. `Enlace` is
one URL per zone (not per classification) pointing at a landing page
(e.g. https://madrid.es/go/ZPAE_Centro) that 403s on scripted fetches
(WAF -- confirmed with curl + browser UA, not a fixable client bug either).
The real thresholds will have to come from that page's content or its
linked Plan Zonal Especifico PDF, fetched by hand or via an authenticated/
browser session -- see docs/data_sources.md for the open question.

Run locally:
    python scripts/01_fetch_zpae.py
"""

import shutil
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import geopandas as gpd

ZIP_URL = (
    "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/"
    "MEDIO_AMBIENTE/INFORMACION_ACUSTICA/ZPAE/ZPAE.zip"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "zpae"
RAW_DIR.mkdir(parents=True, exist_ok=True)
EXTRACT_DIR = RAW_DIR / "_zip_extract"

EXPECTED_ZONE_COUNT = 4

zip_path = RAW_DIR / "ZPAE.zip"
print(f"Downloading {ZIP_URL} ...")
urlretrieve(ZIP_URL, zip_path)

if EXTRACT_DIR.exists():
    shutil.rmtree(EXTRACT_DIR)
EXTRACT_DIR.mkdir(parents=True)

# One file inside the zip (a .lyrx style file) has a non-UTF-8 filename and
# fails to extract -- skip it, it's a QGIS/ArcGIS style resource, not data.
with zipfile.ZipFile(zip_path) as zf:
    for member in zf.namelist():
        try:
            zf.extract(member, EXTRACT_DIR)
        except (UnicodeEncodeError, OSError) as e:
            print(f"  [skip] {member!r} ({e})")

shp_dir = EXTRACT_DIR / "ZPAE"

# --- Zone boundaries (ambitos) ---
ambitos = gpd.read_file(shp_dir / "ZPAE.shp")
print(f"\nZone boundaries (ZPAE.shp): {len(ambitos)} polygons, crs={ambitos.crs}")
zones_present = set(ambitos["ZPAE"])
print(f"Zones present: {sorted(zones_present)}")
if len(zones_present) != EXPECTED_ZONE_COUNT:
    print(f"[!] Expected {EXPECTED_ZONE_COUNT} zones, found {len(zones_present)}.")

ambitos_out = RAW_DIR / "zpae_ambitos.geojson"
ambitos.to_file(ambitos_out, driver="GeoJSON")
print(f"Saved to {ambitos_out}")

# --- Per-street classification ---
clasif = gpd.read_file(shp_dir / "ZPAE_clasificacion.shp")
print(f"\nClassification (ZPAE_clasificacion.shp): {len(clasif)} line "
      f"segments, crs={clasif.crs}, geom types={clasif.geom_type.unique().tolist()}")

clasif_out = RAW_DIR / "zpae_clasificacion.geojson"
clasif.to_file(clasif_out, driver="GeoJSON")
print(f"Saved to {clasif_out}")

clasif_zones = set(clasif["ZPAE"])
if clasif_zones != zones_present:
    print(f"[!] ZPAE.shp and ZPAE_clasificacion.shp spell zone names "
          f"differently -- don't join on ZPAE text directly:\n"
          f"    ambitos:   {sorted(zones_present)}\n"
          f"    clasif:    {sorted(clasif_zones)}")

print("\n--- Zone / classification / link (Enlace has no metre numbers --"
      " it's a landing page URL that 403s scripted fetches) ---")
seen = set()
for _, row in clasif.iterrows():
    key = (row["ZPAE"], row["Clasifica"])
    if key not in seen:
        seen.add(key)
        print(f"[{key[0]} / {key[1]}] -> {row['Enlace']}")

print(
    "\n[!] No layer, anywhere in this dataset, carries a numeric metre "
    "threshold. The real thresholds must come from the Plan Zonal "
    "Especifico content behind each Enlace link, which needs manual/"
    "browser retrieval -- see docs/data_sources.md."
)
